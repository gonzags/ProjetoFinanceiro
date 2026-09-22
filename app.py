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
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile, status
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

# Conjunto de rotas acessíveis sem autenticação
AUTH_PUBLIC_PATHS: frozenset = frozenset({
    "/login", "/register",
    "/auth/google", "/auth/google/callback",
    "/favicon.ico",
    "/health",
    "/api/status",
})

@app.middleware("http")
async def auth_gate(request: Request, call_next):
    """Portão de autenticação: redireciona rotas protegidas se não houver sessão válida."""
    path = request.url.path
    # Sempre libera rotas públicas e arquivos estáticos
    if (
        not ENABLE_AUTH
        or path.startswith("/static")
        or path in AUTH_PUBLIC_PATHS
    ):
        return await call_next(request)

    user = await get_current_user(request)
    if not user:
        if path.startswith("/api/"):
            return JSONResponse(
                {"error": "Não autenticado. Faça login para acessar."},
                status_code=status.HTTP_401_UNAUTHORIZED
            )
        next_url = request.url.path
        return RedirectResponse(
            url=f"/login?next={next_url}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    return await call_next(request)

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
    # Campos de identificação
    name: Optional[str] = None
    age: Optional[int] = None
    occupation: Optional[str] = None
    user_type: Optional[str] = 'pf'          # pf / pj
    marital_status: Optional[str] = None     # solteiro / casado / ...
    dependents: Optional[int] = 0
    work_regime: Optional[str] = None        # clt / pj_mei / autonomo / ...
    # Renda
    monthly_income: Optional[float] = None
    extra_income: Optional[float] = None
    income_list: Optional[List[Dict[str, Any]]] = None  # [{name, amount, type, months_remaining}]
    saved_amount: Optional[float] = None
    saved_destination: Optional[str] = None
    # Despesas
    fixed_expenses_val: Optional[float] = None
    fixed_expenses_list: Optional[List[Dict[str, Any]]] = None  # [{name, amount, category}]
    variable_expenses_val: Optional[float] = None
    variable_expense_averages: Optional[Dict[str, float]] = None  # {alimentacao_fora, transporte, ...}
    # Investimentos
    invests: Optional[str] = None
    investment_types: Optional[List[str]] = None
    risk_tolerance: Optional[str] = None
    # Objetivo
    goal_type: Optional[str] = None
    goal_title: Optional[str] = None
    goal_target_amount: Optional[float] = None
    goal_target_date: Optional[str] = None   # formato 'YYYY-MM-DD'
    goal_current_amount: Optional[float] = None
    # Cartões, contas, dívidas, patrimônio
    cards: Optional[List[Dict[str, Any]]] = None
    bank_accounts: Optional[List[Dict[str, Any]]] = None
    debts: Optional[List[Dict[str, Any]]] = None
    assets: Optional[List[Dict[str, Any]]] = None
    # PJ
    pj_data: Optional[Dict[str, Any]] = None
    # Consentimento
    data_consent: Optional[bool] = False

class CreditCardInput(BaseModel):
    name: str
    bank: Optional[str] = None
    closing_day: int
    due_day: int
    credit_limit: float = 0.0
    current_balance: float = 0.0

class BankAccountInput(BaseModel):
    bank_name: str
    account_type: str = 'corrente'
    balance_approx: float = 0.0

class UserDebtInput(BaseModel):
    description: str
    debt_type: str
    total_amount: float
    monthly_payment: float
    installments_remaining: Optional[int] = None
    interest_rate_monthly: Optional[float] = None
    credit_score_approx: Optional[str] = None

class UserAssetInput(BaseModel):
    asset_type: str
    description: Optional[str] = None
    estimated_value: Optional[float] = None
    financed_value: Optional[float] = None
    monthly_payment: Optional[float] = None
    installments_remaining: Optional[int] = None

class VariableAveragesInput(BaseModel):
    alimentacao_fora: float = 0.0
    transporte: float = 0.0
    lazer: float = 0.0
    vestuario: float = 0.0
    outros: float = 0.0

class PJProfileInput(BaseModel):
    cnpj: Optional[str] = None
    regime_tributario: Optional[str] = None
    business_type: Optional[str] = None
    monthly_revenue_avg: Optional[float] = None
    prolabore: Optional[float] = None
    payroll_total: Optional[float] = None
    tax_monthly: Optional[float] = None
    operational_costs: Optional[float] = None
    partner_count: int = 1

class CardBalancePatchInput(BaseModel):
    current_balance: float

class ExpenseCategoryInput(BaseModel):
    name: str
    category: str
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: int = 0

class ExpenseEntryInput(BaseModel):
    budget_month_id: int
    description: str
    amount: float = Field(..., gt=0)
    expense_type: str = Field("fixed", pattern="^(fixed|variable|debt|card)$")
    category_id: Optional[int] = None
    due_date: Optional[str] = None
    is_paid: bool = False
    installment_current: Optional[int] = None
    installment_total: Optional[int] = None
    notes: Optional[str] = None
    id: Optional[int] = None

class IncomeEntryInput(BaseModel):
    budget_month_id: int
    description: str
    amount: float = Field(..., gt=0)
    income_type: str = Field("salary", pattern="^(salary|extra|benefit|investment_return|other)$")
    is_received: bool = False
    received_at: Optional[str] = None
    notes: Optional[str] = None
    id: Optional[int] = None

class GoalInput(BaseModel):
    title: str
    goal_type: str = Field(..., pattern="^(emergencia|imovel|aposentadoria|viagem|divida|independencia|outro)$")
    target_amount: Optional[float] = Field(None, gt=0)
    target_date: Optional[str] = None
    current_amount: float = 0.0
    monthly_contribution: float = 0.0
    priority: int = 1
    notes: Optional[str] = None
    id: Optional[int] = None


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
    await db_manager.update_last_login(user["id"])
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
    await db_manager.update_last_login(user["id"])
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
        # Salvar objetivo financeiro se fornecido
        if data.goal_type and data.goal_target_amount and uid:
            from datetime import date as _date
            target_date = None
            if data.goal_target_date:
                try:
                    target_date = _date.fromisoformat(data.goal_target_date)
                except (ValueError, TypeError):
                    target_date = None
            goal_payload = {
                'title': data.goal_title or data.goal_type,
                'goal_type': data.goal_type,
                'target_amount': data.goal_target_amount,
                'target_date': target_date,
                'current_amount': data.goal_current_amount or 0,
            }
            if hasattr(db_manager, 'upsert_financial_goal'):
                await db_manager.upsert_financial_goal(uid, goal_payload)
            else:
                db_manager.demo_manager.upsert_financial_goal(uid, goal_payload)
                
        summary = await db_manager.get_financial_summary("Outubro", user_id=uid)
    else:
        summary = await db_manager.get_financial_summary("Outubro")

    return {
        "status": "success",
        "is_draft": is_draft,
        "onboarding_completed": not is_draft,
        "summary": summary
    }


@app.post("/api/onboarding/reseed")
async def reseed_onboarding_entries(request: Request):
    """Re-semeia income_entries e expense_entries a partir do perfil de onboarding salvo.
    Util para usuarios que ja concluiram o onboarding mas nao tem lancamentos no mes atual."""
    user = await get_current_user(request)
    if ENABLE_AUTH and not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacao obrigatoria.")
    uid = user["id"] if user else None
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario nao identificado.")

    profile = await db_manager.get_onboarding_profile(uid)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perfil de onboarding nao encontrado.")

    payload = profile
    if isinstance(payload, dict) and "onboarding_answers" in payload:
        payload = payload["onboarding_answers"]

    if db_manager.is_connected and db_manager.pool:
        await db_manager._seed_entries_from_onboarding(uid, payload)

    return {"status": "ok", "message": "Lancamentos do mes atual re-semeados com sucesso."}


# -----------------------------------------------------------------------------
# Rotas Web (Jinja2)
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Dashboard principal — exige onboarding concluído."""
    user = await get_current_user(request) if ENABLE_AUTH else None

    # Redireciona para onboarding se ainda não concluído (com auth ativa)
    if ENABLE_AUTH and user and not user.get("onboarding_completed"):
        return RedirectResponse(url="/onboarding", status_code=status.HTTP_303_SEE_OTHER)

    now = datetime.now(timezone.utc)

    # Usuário autenticado com onboarding completo → dados reais
    if user and user.get("onboarding_completed"):
        user_id = user["id"]
        first_name = user["name"].split()[0] if user.get("name") else "Usuário"
        greeting = f"Bem-vindo de volta, {first_name}!"
        is_returning = True
        summary = await db_manager.get_monthly_summary(user_id, now.year, now.month)
    else:
        # Novo usuário (sem auth ou sem onboarding): dashboard vazio — sem seed data
        user_id = None
        is_returning = False
        first_name = "Usuário"
        greeting = "Bem-vindo ao Ledger Horizon!"
        summary = None   # JS mostrará estado vazio, não seed


    # Calcular horizon do objetivo real
    target_liberty = "—"
    months_remaining = "—"
    if user and user.get('onboarding_completed'):
        active_goal = None
        if hasattr(db_manager, 'get_active_goal'):
            active_goal = await db_manager.get_active_goal(user['id'])
        if active_goal and active_goal.get('target_date'):
            from datetime import date
            target_dt = active_goal['target_date']
            if hasattr(target_dt, 'date'):
                target_dt = target_dt.date()
            today = date.today()
            months_remaining = max(0, (target_dt.year - today.year)*12 + (target_dt.month - today.month))
            month_names = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                           'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
            target_liberty = f"{month_names[target_dt.month-1]} de {target_dt.year}"

    status_badge = db_manager.get_connection_status()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "user_name": first_name,
            "greeting": greeting,
            "is_returning": is_returning,
            "summary": summary,
            "status_badge": status_badge,
            "current_year": now.year,
            "current_month": now.month,
            "enable_auth": ENABLE_AUTH,
            "target_liberty": target_liberty,
            "months_remaining": months_remaining,
        }
    )


# -----------------------------------------------------------------------------
# Endpoints REST API
# -----------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """Liveness probe para o Docker Healthcheck e orquestradores."""
    return {"status": "ok"}


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
    """Retorna KPIs do mês — apenas para usuários com onboarding concluído."""
    user = await get_request_user(request)

    # Sem usuário autenticado: retorna zeros (sem seed data)
    if not user or not user.get("onboarding_completed"):
        return {"summary": {}, "metrics": {}, "empty": True}

    uid = user["id"]
    summary = await db_manager.get_financial_summary(month, user_id=uid)
    # Enriquecer summary com perfil completo (income_list, debts, etc.)
    try:
        full_profile = await db_manager.get_complete_financial_profile(uid)
        income_list = full_profile.get('profile', {}).get('income_list', [])
        debts_detail = full_profile.get('debts', [])
        # Recalcular total de renda usando income_list se disponível
        if income_list:
            total_income_new = sum(float(s.get('amount', 0)) for s in income_list)
            summary['total_income'] = total_income_new
        # Recalcular debts usando dívidas reais
        if debts_detail:
            debts_new = sum(float(d.get('monthly_payment', 0)) for d in debts_detail)
            summary['debts_total'] = debts_new
    except Exception as e:
        logger.warning(f"KPIs: não foi possível enriquecer com perfil completo: {e}")

    total_income = summary.get("total_income", 0)
    debts = summary.get("debts_total", 0)
    free_pct = max(0.0, min(100.0, round(((total_income - debts) / total_income) * 100, 1))) if total_income > 0 else 0.0

    return {
        "summary": summary,
        "metrics": {
            "fixed_ratio_pct": round((summary.get("fixed_costs", 0) / total_income) * 100, 1) if total_income > 0 else 0.0,
            "debt_ratio_pct": round((debts / total_income) * 100, 1) if total_income > 0 else 0.0,
            "surplus_ratio_pct": round((summary.get("net_surplus", 0) / total_income) * 100, 1) if total_income > 0 else 0.0,
            "gauge_progress_pct": free_pct,
            "user_display_name": user.get("name", "Usuário")
        }
    }


@app.get("/api/timeline")
async def get_timeline(request: Request):
    """Retorna o fluxo de caixa projetado mês a mês."""
    user = await get_request_user(request)
    uid = user["id"] if user else None
    
    # Enriquecer com perfil completo para projetar rendas temporárias e fim de dívidas
    full_profile = {}
    if uid and user and user.get('onboarding_completed'):
        try:
            full_profile = await db_manager.get_complete_financial_profile(uid)
        except Exception as e:
            logger.warning(f"Timeline: não foi possível obter perfil completo: {e}")
    
    timeline = await db_manager.get_timeline(user_id=uid, full_profile=full_profile)
    return [item.model_dump() for item in timeline]


@app.get("/api/consensus")
async def get_consensus(request: Request, month: str = "Outubro"):
    """Retorna a decisão orçamentária do comitê de IA (via cache ou execução)."""
    user = await get_request_user(request)
    uid = user["id"] if user else None
    summary = await db_manager.get_financial_summary(month, user_id=uid)
    
    if user and user.get('onboarding_completed'):
        try:
            full_profile = await db_manager.get_complete_financial_profile(uid)
            summary['income_list'] = full_profile.get('profile', {}).get('income_list', [])
            summary['debts_detail'] = full_profile.get('debts', [])
            summary['assets'] = full_profile.get('assets', [])
            summary['variable_averages'] = full_profile.get('variable_averages', {})
            summary['credit_cards'] = full_profile.get('credit_cards', [])
            debts_monthly = sum(d.get('monthly_payment', 0) for d in full_profile.get('debts', []))
            summary['debts_total'] = debts_monthly
        except Exception as e:
            logger.warning(f"Não foi possível enriquecer financial_summary: {e}")
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
    
    if user and user.get('onboarding_completed'):
        try:
            full_profile = await db_manager.get_complete_financial_profile(uid)
            summary['income_list'] = full_profile.get('profile', {}).get('income_list', [])
            summary['debts_detail'] = full_profile.get('debts', [])
            summary['assets'] = full_profile.get('assets', [])
            summary['variable_averages'] = full_profile.get('variable_averages', {})
            summary['credit_cards'] = full_profile.get('credit_cards', [])
            debts_monthly = sum(d.get('monthly_payment', 0) for d in full_profile.get('debts', []))
            summary['debts_total'] = debts_monthly
        except Exception as e:
            logger.warning(f"Não foi possível enriquecer financial_summary: {e}")
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
    if uid:
        try:
            cached = await db_manager.get_cached_consensus(uid) if hasattr(db_manager, 'get_cached_consensus') else None
            if not cached:
                pass
            else:
                if hasattr(db_manager, 'invalidate_consensus_cache'):
                    await db_manager.invalidate_consensus_cache(uid)
                elif hasattr(db_manager, 'demo_manager'):
                    db_manager.demo_manager.invalidate_cache(user_id=uid)
        except Exception:
            pass

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


@app.get("/onboarding", response_class=HTMLResponse)
async def get_onboarding_page(request: Request):
    """Página de onboarding standalone com wizard completo."""
    user = await get_current_user(request) if ENABLE_AUTH else None
    if ENABLE_AUTH and not user:
        return RedirectResponse(url="/login?next=/onboarding", status_code=status.HTTP_303_SEE_OTHER)
    if user and user.get("onboarding_completed"):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    now = datetime.now(timezone.utc)
    name = user["name"] if user else "Usuário"
    first_name = name.split()[0] if name else "Usuário"

    return templates.TemplateResponse(
        request=request,
        name="onboarding.html",
        context={
            "user": user,
            "user_name": name,
            "first_name": first_name,
            "enable_auth": ENABLE_AUTH,
            "current_year": now.year,
            "current_month": now.month,
        }
    )

# =============================================================================
# Endpoints de Orçamento Mensal
# =============================================================================

@app.get("/api/budget/{year}/{month}")
async def get_budget_month(year: int, month: int, request: Request):
    """Resumo financeiro real do mês: receitas, despesas por tipo, saldo."""
    user = await get_request_user(request)
    user_id = user["id"] if user else None
    bm = await db_manager.get_or_create_budget_month(user_id, year, month)
    summary = await db_manager.get_monthly_summary(user_id, year, month)
    expenses = await db_manager.get_expense_entries(user_id, bm["id"])
    income = await db_manager.get_income_entries(user_id, bm["id"])
    return {
        "budget_month": bm,
        "summary": summary,
        "expenses": expenses,
        "income": income,
    }

@app.post("/api/budget/{year}/{month}/close")
async def close_budget_month(year: int, month: int, request: Request):
    """Fecha o mês tornando-o somente-leitura."""
    user = await get_request_user(request)
    user_id = user["id"] if user else None
    await db_manager.close_budget_month(user_id, year, month)
    return {"status": "closed", "year": year, "month": month}

# =============================================================================
# Endpoints de Categorias de Despesa
# =============================================================================

@app.get("/api/expenses/categories")
async def list_expense_categories(request: Request):
    user = await get_request_user(request)
    cats = await db_manager.get_expense_categories(user["id"] if user else 0)
    return cats

@app.post("/api/expenses/categories", status_code=status.HTTP_201_CREATED)
async def create_expense_category(data: ExpenseCategoryInput, request: Request):
    user = await get_request_user(request)
    cat = await db_manager.create_expense_category(user["id"] if user else 0, data.model_dump())
    return cat

@app.patch("/api/expenses/categories/{cat_id}")
async def update_expense_category(cat_id: int, data: ExpenseCategoryInput, request: Request):
    user = await get_request_user(request)
    await db_manager.update_expense_category(user["id"] if user else 0, cat_id, data.model_dump())
    return {"status": "updated", "id": cat_id}

@app.delete("/api/expenses/categories/{cat_id}")
async def delete_expense_category(cat_id: int, request: Request):
    user = await get_request_user(request)
    await db_manager.delete_expense_category(user["id"] if user else 0, cat_id)
    return {"status": "deleted", "id": cat_id}

# =============================================================================
# Endpoints de Lançamentos de Despesa
# =============================================================================

@app.get("/api/expenses/{year}/{month}")
async def list_expenses(year: int, month: int, request: Request):
    user = await get_request_user(request)
    user_id = user["id"] if user else 0
    bm = await db_manager.get_or_create_budget_month(user_id, year, month)
    entries = await db_manager.get_expense_entries(user_id, bm["id"])
    return {"budget_month_id": bm["id"], "is_closed": bm["is_closed"], "entries": entries}

@app.post("/api/expenses", status_code=status.HTTP_201_CREATED)
async def upsert_expense(data: ExpenseEntryInput, request: Request):
    user = await get_request_user(request)
    user_id = user["id"] if user else 0
    try:
        entry = await db_manager.upsert_expense_entry(user_id, data.model_dump())
        uid = user_id
        if uid:
            try:
                cached = await db_manager.get_cached_consensus(uid) if hasattr(db_manager, 'get_cached_consensus') else None
                if not cached:
                    pass
                else:
                    if hasattr(db_manager, 'invalidate_consensus_cache'):
                        await db_manager.invalidate_consensus_cache(uid)
                    elif hasattr(db_manager, 'demo_manager'):
                        db_manager.demo_manager.invalidate_cache(user_id=uid)
            except Exception:
                pass
        return entry
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@app.delete("/api/expenses/{entry_id}")
async def delete_expense(entry_id: int, request: Request):
    user = await get_request_user(request)
    user_id = user["id"] if user else 0
    try:
        await db_manager.delete_expense_entry(user_id, entry_id)
        uid = user_id
        if uid:
            try:
                cached = await db_manager.get_cached_consensus(uid) if hasattr(db_manager, 'get_cached_consensus') else None
                if not cached:
                    pass
                else:
                    if hasattr(db_manager, 'invalidate_consensus_cache'):
                        await db_manager.invalidate_consensus_cache(uid)
                    elif hasattr(db_manager, 'demo_manager'):
                        db_manager.demo_manager.invalidate_cache(user_id=uid)
            except Exception:
                pass
        return {"status": "deleted", "id": entry_id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

# =============================================================================
# Endpoints de Receitas
# =============================================================================

@app.get("/api/income/{year}/{month}")
async def list_income(year: int, month: int, request: Request):
    user = await get_request_user(request)
    user_id = user["id"] if user else 0
    bm = await db_manager.get_or_create_budget_month(user_id, year, month)
    entries = await db_manager.get_income_entries(user_id, bm["id"])
    return {"budget_month_id": bm["id"], "is_closed": bm["is_closed"], "entries": entries}

@app.post("/api/income", status_code=status.HTTP_201_CREATED)
async def upsert_income(data: IncomeEntryInput, request: Request):
    user = await get_request_user(request)
    user_id = user["id"] if user else 0
    try:
        entry = await db_manager.upsert_income_entry(user_id, data.model_dump())
        uid = user_id
        if uid:
            try:
                cached = await db_manager.get_cached_consensus(uid) if hasattr(db_manager, 'get_cached_consensus') else None
                if not cached:
                    pass
                else:
                    if hasattr(db_manager, 'invalidate_consensus_cache'):
                        await db_manager.invalidate_consensus_cache(uid)
                    elif hasattr(db_manager, 'demo_manager'):
                        db_manager.demo_manager.invalidate_cache(user_id=uid)
            except Exception:
                pass
        return entry
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@app.delete("/api/income/{entry_id}")
async def delete_income(entry_id: int, request: Request):
    user = await get_request_user(request)
    user_id = user["id"] if user else 0
    try:
        await db_manager.delete_income_entry(user_id, entry_id)
        uid = user_id
        if uid:
            try:
                cached = await db_manager.get_cached_consensus(uid) if hasattr(db_manager, 'get_cached_consensus') else None
                if not cached:
                    pass
                else:
                    if hasattr(db_manager, 'invalidate_consensus_cache'):
                        await db_manager.invalidate_consensus_cache(uid)
                    elif hasattr(db_manager, 'demo_manager'):
                        db_manager.demo_manager.invalidate_cache(user_id=uid)
            except Exception:
                pass
        return {"status": "deleted", "id": entry_id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

# =============================================================================
# Endpoints de Objetivos Financeiros
# =============================================================================

@app.get("/api/goals")
async def get_goal(request: Request):
    user = await get_request_user(request)
    goal = await db_manager.get_active_goal(user["id"] if user else 0)
    return goal or {}

@app.post("/api/goals", status_code=status.HTTP_201_CREATED)
async def upsert_goal(data: GoalInput, request: Request):
    user = await get_request_user(request)
    goal = await db_manager.upsert_goal(user["id"] if user else 0, data.model_dump())
    return goal

@app.delete("/api/goals/{goal_id}")
async def deactivate_goal(goal_id: int, request: Request):
    user = await get_request_user(request)
    await db_manager.deactivate_goal(user["id"] if user else 0, goal_id)
    return {"status": "deactivated", "id": goal_id}

# =============================================================================
# Endpoints de Portfólio de Investimentos
# =============================================================================

@app.get("/api/portfolio")
async def get_portfolio(request: Request):
    """Retorna o portfólio ativo atual."""
    user = await get_request_user(request)
    portfolio = await db_manager.get_active_portfolio(user["id"] if user else 0)
    return portfolio or {}

@app.post("/api/portfolio/generate")
@limiter.limit(os.getenv("RATE_LIMIT_RECALCULATE", "3/hour"))
async def generate_portfolio(request: Request):
    """Dispara nova rodada de consenso para gerar carteira personalizada."""
    user = await get_request_user(request)
    user_id = user["id"] if user else None

    # Carregar contexto real do usuário
    now = datetime.now(timezone.utc)
    summary = await db_manager.get_monthly_summary(user_id, now.year, now.month) if user_id else \
              await db_manager.get_financial_summary("Atual")
    profile = await db_manager.get_onboarding_profile(user_id) if user_id else {}
    goal = await db_manager.get_active_goal(user_id) if user_id else None
    portfolio_history = await db_manager.get_portfolio_history(user_id, limit=3) if user_id else []

    # Enriquecer o summary com contexto do usuário para o prompt da IA
    summary["user_profile"] = profile or {}
    summary["financial_goal"] = goal
    summary["portfolio_history"] = portfolio_history

    result = await consensus_engine.run_consensus_loop(summary, force_recalculate=True, user_id=user_id)
    result_dict = result.model_dump()

    # Construir portfólio a partir da alocação do consenso e do perfil do usuário
    alloc = result_dict.get("allocation", {})
    # O percentual destinado a futuro/poupança é a base do portfólio de investimentos
    pct_savings = float(alloc.get("savings", alloc.get("futuro", 0)))
    monthly_income = float(summary.get("total_income", 0))
    monthly_investment_target = round(monthly_income * (pct_savings / 100), 2) if monthly_income > 0 else 0.0

    # Determinar perfil de risco do usuário para distribuição dos ativos
    profile_payload = (profile or {}).get("payload", profile or {})
    risk_tolerance = profile_payload.get("risk_tolerance", "moderado")

    # Distribuição padrão por perfil de risco (soma = 100%)
    risk_map = {
        "conservador":  {"pct_renda_fixa": 50, "pct_tesouro": 30, "pct_fiis": 10, "pct_acoes": 0,  "pct_reserva_liquida": 10, "pct_cripto": 0},
        "moderado":     {"pct_renda_fixa": 35, "pct_tesouro": 25, "pct_fiis": 15, "pct_acoes": 15, "pct_reserva_liquida": 8,  "pct_cripto": 2},
        "arrojado":     {"pct_renda_fixa": 20, "pct_tesouro": 15, "pct_fiis": 15, "pct_acoes": 40, "pct_reserva_liquida": 5,  "pct_cripto": 5},
        "agressivo":    {"pct_renda_fixa": 10, "pct_tesouro": 10, "pct_fiis": 10, "pct_acoes": 55, "pct_reserva_liquida": 5,  "pct_cripto": 10},
    }
    dist = risk_map.get(risk_tolerance.lower() if risk_tolerance else "moderado", risk_map["moderado"])

    # Calcular meses até o objetivo se disponível
    months_to_goal = None
    if goal and goal.get("target_amount") and goal.get("current_amount") is not None and monthly_investment_target > 0:
        remaining = float(goal["target_amount"]) - float(goal.get("current_amount", 0))
        if remaining > 0:
            months_to_goal = max(1, round(remaining / monthly_investment_target))

    portfolio_data = {
        **dist,
        "monthly_investment_target": monthly_investment_target,
        "emergency_reserve_target": round(monthly_income * 6, 2),
        "months_to_goal": months_to_goal,
        "rationale": f"Perfil {risk_tolerance or 'moderado'} — {result_dict.get('reasoning_summary', '')}".strip(),
    }

    if user_id:
        saved = await db_manager.save_portfolio(user_id, portfolio_data, consensus_record_id=result_dict.get("id"))
        result_dict["portfolio"] = saved
    else:
        result_dict["portfolio"] = portfolio_data

    return result_dict

# =============================================================================
# Forecast (projeção futura)
# =============================================================================

@app.get("/api/forecast/{months}")
async def get_forecast(months: int, request: Request):
    """Projeção financeira mês a mês para os próximos N meses (máx 24)."""
    months = min(months, 24)
    user = await get_request_user(request)
    user_id = user["id"] if user else None
    timeline = await db_manager.get_monthly_timeline(user_id) if user_id else \
               [item.model_dump() for item in await db_manager.get_timeline()]
    return timeline

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8200, reload=True)



# ── Cartões ────────────────────────────────────────────────────────────────
@app.get("/api/profile/me")
async def get_profile_me(request: Request):
    """Retorna perfil completo do usuario (dados do onboarding + users table + cartoes + objetivo)."""
    user = await get_current_user(request)
    if ENABLE_AUTH and not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacao obrigatoria.")
    uid = user["id"] if user else None

    profile_raw = await db_manager.get_onboarding_profile(uid) if uid else {}
    profile = profile_raw or {}
    if isinstance(profile, dict) and "onboarding_answers" in profile:
        profile = profile["onboarding_answers"]

    cards = await db_manager.get_credit_cards(uid) if uid else []
    goal = await db_manager.get_active_goal(uid) if uid else None

    # Recuperar avatar_url da tabela users
    avatar_url = None
    if uid and db_manager.is_connected and db_manager.pool:
        async with db_manager.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT avatar_url, created_at FROM users WHERE id=$1", uid)
            if row:
                avatar_url = row["avatar_url"]
                member_since = row["created_at"].strftime("%B %Y") if row["created_at"] else None
            else:
                member_since = None
    else:
        member_since = None

    return {
        "name": user.get("name") if user else profile.get("name"),
        "email": user.get("email") if user else None,
        "avatar_url": avatar_url,
        "member_since": member_since,
        "user_type": profile.get("user_type", "pf"),
        "age": profile.get("age"),
        "occupation": profile.get("occupation"),
        "marital_status": profile.get("marital_status"),
        "dependents": profile.get("dependents", 0),
        "monthly_income": profile.get("monthly_income", 0),
        "risk_tolerance": profile.get("risk_tolerance", "moderado"),
        "invests": profile.get("invests", "nao_investe"),
        "investment_types": profile.get("investment_types", []),
        "cards": cards,
        "goal": goal,
    }


@app.post("/api/profile/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    """Recebe imagem de perfil, salva em static/uploads/avatars/ e atualiza users.avatar_url."""
    user = await get_current_user(request)
    if ENABLE_AUTH and not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacao obrigatoria.")
    uid = user["id"] if user else None
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    # Validar tipo de arquivo
    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Formato invalido. Use JPEG, PNG, WebP ou GIF.")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    upload_dir = Path("static/uploads/avatars")
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{uid}.{ext}"

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:  # 5 MB max
        raise HTTPException(status_code=400, detail="Imagem muito grande. Maximo 5 MB.")

    with open(dest, "wb") as f:
        f.write(contents)

    avatar_url = f"/static/uploads/avatars/{uid}.{ext}"

    if db_manager.is_connected and db_manager.pool:
        async with db_manager.pool.acquire() as conn:
            await conn.execute("UPDATE users SET avatar_url=$1 WHERE id=$2", avatar_url, uid)

    return {"avatar_url": avatar_url}


@app.get("/api/profile/cards")
async def get_cards(request: Request):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    cards = await db_manager.get_credit_cards(user['id'])
    return JSONResponse(cards)

@app.post("/api/profile/cards")
async def create_card(request: Request, body: CreditCardInput):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    card = await db_manager.upsert_credit_card(user['id'], body.model_dump())
    return JSONResponse(card, status_code=201)

@app.patch("/api/profile/cards/{card_id}")
async def patch_card_balance(request: Request, card_id: str, body: CardBalancePatchInput):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    ok = await db_manager.patch_credit_card_balance(user['id'], card_id, body.current_balance)
    if not ok:
        return JSONResponse({'error': 'not found'}, status_code=404)
    return JSONResponse({'ok': True})

@app.put("/api/profile/cards/{card_id}")
async def update_card(request: Request, card_id: str, body: CreditCardInput):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    card_data = body.model_dump()
    card_data['id'] = card_id
    card = await db_manager.upsert_credit_card(user['id'], card_data)
    return JSONResponse(card)

@app.delete("/api/profile/cards/{card_id}")
async def delete_card(request: Request, card_id: str):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    ok = await db_manager.delete_credit_card(user['id'], card_id)
    return JSONResponse({'ok': ok})

# ── Contas Bancárias ────────────────────────────────────────────────────────
@app.get("/api/profile/accounts")
async def get_accounts(request: Request):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    accounts = await db_manager.get_bank_accounts(user['id'])
    return JSONResponse(accounts)

@app.post("/api/profile/accounts")
async def create_account(request: Request, body: BankAccountInput):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    account = await db_manager.upsert_bank_account(user['id'], body.model_dump())
    return JSONResponse(account, status_code=201)

@app.delete("/api/profile/accounts/{acct_id}")
async def delete_account(request: Request, acct_id: str):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    ok = await db_manager.delete_bank_account(user['id'], acct_id)
    return JSONResponse({'ok': ok})

# ── Dívidas ────────────────────────────────────────────────────────────────
@app.get("/api/profile/debts")
async def get_debts(request: Request):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    debts = await db_manager.get_user_debts(user['id'])
    return JSONResponse(debts)

@app.post("/api/profile/debts")
async def create_debt(request: Request, body: UserDebtInput):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    debt = await db_manager.upsert_user_debt(user['id'], body.model_dump())
    return JSONResponse(debt, status_code=201)

@app.delete("/api/profile/debts/{debt_id}")
async def delete_debt(request: Request, debt_id: str):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    ok = await db_manager.delete_user_debt(user['id'], debt_id)
    return JSONResponse({'ok': ok})

# ── Patrimônio ─────────────────────────────────────────────────────────────
@app.get("/api/profile/assets")
async def get_assets(request: Request):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    assets = await db_manager.get_user_assets(user['id'])
    return JSONResponse(assets)

@app.post("/api/profile/assets")
async def create_asset(request: Request, body: UserAssetInput):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    asset = await db_manager.upsert_user_asset(user['id'], body.model_dump())
    return JSONResponse(asset, status_code=201)

@app.delete("/api/profile/assets/{asset_id}")
async def delete_asset(request: Request, asset_id: str):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    ok = await db_manager.delete_user_asset(user['id'], asset_id)
    return JSONResponse({'ok': ok})

# ── Despesas Variáveis Médias ─────────────────────────────────────────────
@app.get("/api/profile/variable-averages")
async def get_variable_averages(request: Request):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    averages = await db_manager.get_variable_expense_averages(user['id'])
    return JSONResponse(averages)

@app.put("/api/profile/variable-averages")
async def update_variable_averages(request: Request, body: VariableAveragesInput):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    await db_manager.save_variable_expense_averages(user['id'], body.model_dump())
    return JSONResponse({'ok': True})

# ── Perfil PJ ─────────────────────────────────────────────────────────────
@app.get("/api/profile/pj")
async def get_pj(request: Request):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    pj = await db_manager.get_pj_profile(user['id'])
    return JSONResponse(pj or {})

@app.put("/api/profile/pj")
async def update_pj(request: Request, body: PJProfileInput):
    user = getattr(request.state, 'user', None)
    if not user:
        user = await get_current_user(request)
    if not user:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    await db_manager.save_pj_profile(user['id'], body.model_dump())
    return JSONResponse({'ok': True})
