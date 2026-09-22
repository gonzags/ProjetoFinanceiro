"""
app.py - Servidor FastAPI da Plataforma Analítica Financeira (Ledger Horizon)
Rotas Jinja2, API REST assíncrona, rate limiting (SlowAPI), headers de segurança,
autenticação multi-tenant com cookies assinados, CSRF double-submit, OAuth state validation
e wizard de onboarding interativo.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Carregar variáveis de ambiente
load_dotenv()

# Configuração de Logging seguro (sem logar senhas nem dados financeiros sensíveis)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ledger_horizon.app")

from auth import (
    CSRF_COOKIE_NAME,
    OAUTH_STATE_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    create_oauth_state,
    create_session_token,
    exchange_google_code_for_user,
    generate_csrf_token,
    get_current_user,
    get_google_auth_url,
    hash_password,
    is_google_auth_configured,
    validate_secret_key,
    verify_csrf_token,
    verify_oauth_state,
    verify_password,
)
from llm_router import consensus_engine
from utils import db_manager

# Controle de Multi-Tenancy / Autenticação (Padrão: False para regressão zero)
ENABLE_AUTH = os.getenv("ENABLE_AUTH", "False").lower() in ("true", "1", "yes")

# -----------------------------------------------------------------------------
# Rate Limiting (SlowAPI)
# -----------------------------------------------------------------------------
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[os.getenv("RATE_LIMIT_DEFAULT", "60/minute")]
)

# -----------------------------------------------------------------------------
# Ciclo de Vida da Aplicação (Lifespan)
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando Ledger Horizon Analytics Engine...")
    validate_secret_key()
    await db_manager.connect()
    yield
    logger.info("Encerrando Ledger Horizon...")
    await db_manager.disconnect()

# -----------------------------------------------------------------------------
# Instância FastAPI e Middlewares de Segurança
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Ledger Horizon - Financial Analytics Platform",
    description="Plataforma Analítica Financeira com Motor de Consenso Multi-IA e Design Ledger Horizon",
    version="4.0.0",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("DEBUG", "False").lower() == "true" else None,
    redoc_url=None
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS explícito
_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:8080,http://127.0.0.1:8080,http://localhost:8200,http://127.0.0.1:8200")
_allowed_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Middleware de Segurança e Headers HTTP
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Exceção não tratada na requisição {request.url.path}: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Erro interno no servidor de processamento analítico."}
        )

# Arquivos estáticos e templates
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# -----------------------------------------------------------------------------
# Modelos Pydantic para Requisições
# -----------------------------------------------------------------------------
class QuestionnaireInput(BaseModel):
    salary_net: Optional[float] = Field(None, ge=0.0)
    fixed_expenses: Optional[List[Dict[str, Any]]] = None
    card_schedules: Optional[Dict[str, Any]] = None
    one_off_commitments: Optional[List[Dict[str, Any]]] = None


class MethodologyRequest(BaseModel):
    methodology: str = Field("50-30-20", description="50-30-20, 60-20-20, 70-20-10 ou zero_based")
    income: Optional[float] = None


class OnboardingInput(BaseModel):
    is_draft: bool = False
    name: Optional[str] = None
    age: Optional[int] = None
    occupation: Optional[str] = None
    monthly_income: Optional[float] = None
    extra_income: Optional[float] = None
    fixed_expenses_val: Optional[float] = None
    variable_expenses_val: Optional[float] = None
    saved_amount: Optional[float] = None
    saved_destination: Optional[str] = None
    invests: Optional[str] = None
    investment_types: Optional[List[str]] = None
    risk_tolerance: Optional[str] = None


# -----------------------------------------------------------------------------
# Helper de Autenticação para Endpoints da API
# -----------------------------------------------------------------------------
async def get_request_user(request: Request) -> Optional[Dict[str, Any]]:
    """Retorna o usuário autenticado ou lança 401 se ENABLE_AUTH estiver ativo."""
    if not ENABLE_AUTH:
        return None
    user = await get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação obrigatória. Por favor, efetue login."
        )
    return user


# -----------------------------------------------------------------------------
# Rotas de Autenticação (Login, Cadastro, Logout e Google OAuth)
# -----------------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    if ENABLE_AUTH:
        user = await get_current_user(request)
        if user:
            return RedirectResponse(url=next or "/", status_code=status.HTTP_303_SEE_OTHER)

    csrf_token = generate_csrf_token()
    error_msg = request.query_params.get("error")
    response = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "csrf_token": csrf_token,
            "active_tab": "login",
            "next_url": next,
            "error": error_msg,
            "google_auth_enabled": is_google_auth_configured()
        }
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=7200,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1")
    )
    return response


@app.post("/login")
@limiter.limit("10/minute")
async def handle_login(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip()
    password = str(form.get("password", ""))
    csrf_form = form.get("csrf_token")
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    next_url = request.query_params.get("next", "/")

    if not verify_csrf_token(csrf_form, csrf_cookie):
        new_csrf = generate_csrf_token()
        resp = templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "csrf_token": new_csrf,
                "active_tab": "login",
                "next_url": next_url,
                "error": "Token de validação CSRF inválido ou expirado. Tente novamente.",
                "google_auth_enabled": is_google_auth_configured()
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )
        resp.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=new_csrf,
            max_age=7200,
            httponly=True,
            samesite="lax",
            secure=os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1")
        )
        return resp

    user = await db_manager.get_user_by_email(email)
    if not user or not verify_password(password, user.get("password_hash")):
        new_csrf = generate_csrf_token()
        resp = templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "csrf_token": new_csrf,
                "active_tab": "login",
                "next_url": next_url,
                "error": "Credenciais inválidas. Verifique seu e-mail e senha.",
                "google_auth_enabled": is_google_auth_configured()
            },
            status_code=status.HTTP_401_UNAUTHORIZED
        )
        resp.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=new_csrf,
            max_age=7200,
            httponly=True,
            samesite="lax",
            secure=os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1")
        )
        return resp

    token = create_session_token(user["id"])
    response = RedirectResponse(url=next_url or "/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=14 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1")
    )
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, next: str = "/"):
    if ENABLE_AUTH:
        user = await get_current_user(request)
        if user:
            return RedirectResponse(url=next or "/", status_code=status.HTTP_303_SEE_OTHER)

    csrf_token = generate_csrf_token()
    error_msg = request.query_params.get("error")
    response = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "csrf_token": csrf_token,
            "active_tab": "register",
            "next_url": next,
            "error": error_msg,
            "google_auth_enabled": is_google_auth_configured()
        }
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=7200,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1")
    )
    return response


@app.post("/register")
@limiter.limit("10/minute")
async def handle_register(request: Request):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    email = str(form.get("email", "")).strip()
    password = str(form.get("password", ""))
    csrf_form = form.get("csrf_token")
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    next_url = request.query_params.get("next", "/")

    if not verify_csrf_token(csrf_form, csrf_cookie):
        new_csrf = generate_csrf_token()
        resp = templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "csrf_token": new_csrf,
                "active_tab": "register",
                "next_url": next_url,
                "error": "Token de validação CSRF inválido ou expirado. Tente novamente.",
                "google_auth_enabled": is_google_auth_configured()
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )
        resp.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=new_csrf,
            max_age=7200,
            httponly=True,
            samesite="lax",
            secure=os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1")
        )
        return resp

    if not name or not email or not password or len(password) < 6:
        new_csrf = generate_csrf_token()
        resp = templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "csrf_token": new_csrf,
                "active_tab": "register",
                "next_url": next_url,
                "error": "Preencha todos os campos. A senha deve possuir no mínimo 6 caracteres.",
                "google_auth_enabled": is_google_auth_configured()
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )
        resp.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=new_csrf,
            max_age=7200,
            httponly=True,
            samesite="lax",
            secure=os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1")
        )
        return resp

    existing = await db_manager.get_user_by_email(email)
    if existing:
        new_csrf = generate_csrf_token()
        resp = templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "csrf_token": new_csrf,
                "active_tab": "register",
                "next_url": next_url,
                "error": "Este e-mail já está cadastrado. Por favor, acesse a aba Entrar.",
                "google_auth_enabled": is_google_auth_configured()
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )
        resp.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=new_csrf,
            max_age=7200,
            httponly=True,
            samesite="lax",
            secure=os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1")
        )
        return resp

    pwd_hash = hash_password(password)
    new_user = await db_manager.create_user(email=email, password_hash=pwd_hash, name=name)
    token = create_session_token(new_user["id"])

    response = RedirectResponse(url=next_url or "/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=14 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1")
    )
    return response


@app.post("/logout")
async def handle_logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response


@app.get("/auth/google")
async def google_auth_redirect(request: Request, next: str = "/"):
    if not is_google_auth_configured():
        raise HTTPException(status_code=404, detail="Google OAuth não está configurado.")
    state = create_oauth_state()
    redirect_uri = str(request.url_for("google_auth_callback"))
    auth_url = get_google_auth_url(redirect_uri=redirect_uri, state=state)
    response = RedirectResponse(url=auth_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=state,
        max_age=300,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1")
    )
    return response


@app.get("/auth/google/callback", name="google_auth_callback")
async def google_auth_callback(request: Request):
    if not is_google_auth_configured():
        raise HTTPException(status_code=404, detail="Google OAuth não está configurado.")

    code = request.query_params.get("code")
    state_query = request.query_params.get("state")
    state_cookie = request.cookies.get(OAUTH_STATE_COOKIE_NAME)

    if not verify_oauth_state(state_query, state_cookie):
        logger.warning("Falha de validação de state no callback OAuth do Google (state mismatch ou expirado).")
        resp = RedirectResponse(
            url="/login?error=Validacao+de+seguranca+OAuth+invalida+(state+mismatch)",
            status_code=status.HTTP_303_SEE_OTHER
        )
        resp.delete_cookie(key=OAUTH_STATE_COOKIE_NAME)
        return resp

    if not code:
        resp = RedirectResponse(
            url="/login?error=Codigo+de+autorizacao+nao+fornecido",
            status_code=status.HTTP_303_SEE_OTHER
        )
        resp.delete_cookie(key=OAUTH_STATE_COOKIE_NAME)
        return resp

    redirect_uri = str(request.url_for("google_auth_callback"))
    user_data = await exchange_google_code_for_user(code, redirect_uri)
    if not user_data or not user_data.get("email"):
        resp = RedirectResponse(
            url="/login?error=Falha+na+comunicacao+com+o+Google",
            status_code=status.HTTP_303_SEE_OTHER
        )
        resp.delete_cookie(key=OAUTH_STATE_COOKIE_NAME)
        return resp

    email = user_data["email"]
    sub = user_data.get("sub")
    name = user_data.get("name", "Usuário Google")

    user = await db_manager.get_user_by_google_sub(sub) if sub else None
    if not user:
        user = await db_manager.get_user_by_email(email)
        if not user:
            user = await db_manager.create_user(
                email=email,
                password_hash=None,
                name=name,
                auth_provider="google",
                google_sub=sub
            )

    token = create_session_token(user["id"])
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=OAUTH_STATE_COOKIE_NAME)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=14 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "False").lower() in ("true", "1")
    )
    return response


# -----------------------------------------------------------------------------
# Rotas de Onboarding (API)
# -----------------------------------------------------------------------------
@app.get("/api/onboarding")
async def get_onboarding_status(request: Request):
    user = await get_current_user(request)
    if ENABLE_AUTH and not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação obrigatória.")
    uid = user["id"] if user else None
    profile = await db_manager.get_onboarding_profile(uid) if uid else None
    return {
        "user": user,
        "profile": profile
    }


@app.post("/api/onboarding")
async def save_onboarding(request: Request, data: OnboardingInput):
    user = await get_current_user(request)
    if ENABLE_AUTH and not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação obrigatória.")

    uid = user["id"] if user else None
    payload = data.model_dump(exclude_none=True)
    is_draft = data.is_draft

    if uid:
        await db_manager.save_onboarding_profile(uid, payload, is_draft=is_draft)
        summary = await db_manager.get_financial_summary("Outubro", user_id=uid)
    else:
        summary = await db_manager.get_financial_summary("Outubro")

    return {
        "status": "success",
        "is_draft": is_draft,
        "onboarding_completed": not is_draft,
        "summary": summary
    }


# -----------------------------------------------------------------------------
# Rotas Web (Jinja2)
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Renderiza a interface principal do Ledger Horizon."""
    user = None
    user_id = None
    if ENABLE_AUTH:
        user = await get_current_user(request)
        if not user:
            return RedirectResponse(url="/login?next=/", status_code=status.HTTP_303_SEE_OTHER)
        user_id = user["id"]
        user_name = user["name"]
    else:
        user_name = db_manager.get_display_name()

    summary = await db_manager.get_financial_summary("Outubro", user_id=user_id)
    status_badge = db_manager.get_connection_status()

    # Calcular contagem regressiva para Abril/2027 (mês da libertação financeira)
    target_liberty = "Abril de 2027"
    months_remaining = 7  # Outubro a Abril

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "user_name": user_name,
            "summary": summary,
            "status_badge": status_badge,
            "target_liberty": target_liberty,
            "months_remaining": months_remaining,
        }
    )


# -----------------------------------------------------------------------------
# Endpoints REST API
# -----------------------------------------------------------------------------
@app.get("/api/status")
async def get_system_status():
    """Retorna o status de conexão ao data warehouse / modo demo."""
    return {
        "status_badge": db_manager.get_connection_status(),
        "is_connected": db_manager.is_connected,
        "circuit_breaker_active_cooldowns": {
            pid: cb_time for pid, cb_time in consensus_engine.circuit_breaker.cooldown_until.items()
        }
    }


@app.get("/api/kpis")
async def get_kpis(request: Request, month: str = "Outubro"):
    """Retorna os indicadores chave de desempenho para o mês solicitado."""
    user = await get_request_user(request)
    uid = user["id"] if user else None

    summary = await db_manager.get_financial_summary(month, user_id=uid)
    total_income = summary["total_income"]
    debts = summary["debts_total"]

    # Progresso dinâmico de renda livre em relação às dívidas
    free_pct = max(0.0, min(100.0, round(((total_income - debts) / total_income) * 100, 1))) if total_income > 0 else 0.0

    return {
        "summary": summary,
        "metrics": {
            "fixed_ratio_pct": round((summary["fixed_costs"] / total_income) * 100, 1) if total_income > 0 else 0.0,
            "debt_ratio_pct": round((debts / total_income) * 100, 1) if total_income > 0 else 0.0,
            "surplus_ratio_pct": round((summary["net_surplus"] / total_income) * 100, 1) if total_income > 0 else 0.0,
            "vr_benefit": 500.00,
            "liberty_horizon_month": "Abril 2027",
            "months_to_liberty": 7,
            "gauge_progress_pct": free_pct,
            "user_display_name": user["name"] if user else db_manager.get_display_name()
        }
    }


@app.get("/api/timeline")
async def get_timeline(request: Request):
    """Retorna o fluxo de caixa projetado mês a mês (Outubro a Agosto)."""
    user = await get_request_user(request)
    uid = user["id"] if user else None
    timeline = await db_manager.get_timeline(user_id=uid)
    return [item.model_dump() for item in timeline]


@app.get("/api/consensus")
async def get_consensus(request: Request, month: str = "Outubro"):
    """Retorna a decisão orçamentária do comitê de IA (via cache ou execução)."""
    user = await get_request_user(request)
    uid = user["id"] if user else None
    summary = await db_manager.get_financial_summary(month, user_id=uid)
    result = await consensus_engine.run_consensus_loop(summary, force_recalculate=False, user_id=uid)
    return result.model_dump()


@app.post("/api/consensus/recalculate")
@limiter.limit(os.getenv("RATE_LIMIT_RECALCULATE", "3/hour"))
async def recalculate_consensus(request: Request, month: str = "Outubro"):
    """
    Força a reexecução do loop de consenso multi-IA.
    Limitado a 3 requisições por hora por IP para proteção estrita de cotas gratuitas.
    """
    user = await get_request_user(request)
    uid = user["id"] if user else None
    summary = await db_manager.get_financial_summary(month, user_id=uid)
    result = await consensus_engine.run_consensus_loop(summary, force_recalculate=True, user_id=uid)
    return result.model_dump()


@app.post("/api/questionnaire")
async def update_questionnaire(request: Request, data: QuestionnaireInput):
    """
    Atualiza as variáveis orçamentárias pelo questionário interativo.
    Invalida automaticamente o cache de consenso do Postgres.
    """
    user = await get_request_user(request)
    uid = user["id"] if user else None
    update_dict = data.model_dump(exclude_none=True)
    await db_manager.update_financial_inputs(update_dict, user_id=uid)

    # Recalcular resumo do mês atual
    summary = await db_manager.get_financial_summary("Outubro", user_id=uid)
    return {
        "status": "success",
        "message": "Dados financeiros atualizados com sucesso e cache invalidado.",
        "updated_summary": summary
    }


@app.post("/api/methodology")
async def calculate_methodology(request: Request, req: MethodologyRequest):
    """
    Calcula as cotas de alocação de acordo com o seletor de metodologias:
    - 50-30-20
    - 60-20-20
    - 70-20-10
    - Base Zero
    """
    user = await get_request_user(request)
    uid = user["id"] if user else None
    summary = await db_manager.get_financial_summary("Outubro", user_id=uid)
    income = req.income or summary["total_income"]

    if req.methodology == "60-20-20":
        nec_pct, des_pct, fut_pct = 60.0, 20.0, 20.0
    elif req.methodology == "70-20-10":
        nec_pct, des_pct, fut_pct = 70.0, 20.0, 10.0
    elif req.methodology == "zero_based":
        # Aloca 100% dos recursos nas categorias reais
        fixed = summary["fixed_costs"]
        debts = summary["debts_total"] + summary["special_events"]
        surplus = max(0.0, income - fixed - debts)
        return {
            "methodology": "zero_based",
            "allocations": {
                "necessidades": round(fixed, 2),
                "desejos": round(summary["special_events"], 2),
                "futuro": round(debts - summary["special_events"], 2),
                "reserva_disponivel": round(surplus, 2)
            },
            "percentages": {
                "necessidades": round((fixed / income) * 100, 1),
                "desejos": round((summary["special_events"] / income) * 100, 1),
                "futuro": round(((debts - summary["special_events"]) / income) * 100, 1),
                "reserva_disponivel": round((surplus / income) * 100, 1)
            }
        }
    else:  # Padrão 50-30-20
        nec_pct, des_pct, fut_pct = 50.0, 30.0, 20.0

    return {
        "methodology": req.methodology,
        "percentages": {
            "necessidades": nec_pct,
            "desejos": des_pct,
            "futuro": fut_pct
        },
        "allocations": {
            "necessidades": round(income * (nec_pct / 100.0), 2),
            "desejos": round(income * (des_pct / 100.0), 2),
            "futuro": round(income * (fut_pct / 100.0), 2)
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8200, reload=True)
