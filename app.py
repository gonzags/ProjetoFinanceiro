"""
app.py - Servidor FastAPI da Plataforma Analítica Financeira (Ledger Horizon)
Rotas Jinja2, API REST assíncrona, rate limiting (SlowAPI), headers de segurança e gerenciamento de estado.
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
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Carregar variáveis de ambiente
load_dotenv()

# Configuração de Logging seguro (sem logar dados financeiros brutos)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ledger_horizon.app")

from llm_router import consensus_engine
from utils import db_manager

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    except Exception as e:
        logger.error(f"Exceção não tratada na requisição {request.url.path}: {e}")
        # Nunca expor stack trace ao cliente em produção (claudeaudita.pdf seção 5)
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


# -----------------------------------------------------------------------------
# Rotas Web (Jinja2)
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Renderiza a interface principal do Ledger Horizon."""
    summary = await db_manager.get_financial_summary("Outubro")
    status_badge = db_manager.get_connection_status()
    
    # Calcular contagem regressiva para Abril/2027 (mês da libertação financeira)
    target_liberty = "Abril de 2027"
    months_remaining = 7  # Outubro a Abril

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user_name": "Pedro Silva",
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
async def get_kpis(month: str = "Outubro"):
    """Retorna os indicadores chave de desempenho para o mês solicitado."""
    summary = await db_manager.get_financial_summary(month)
    return {
        "summary": summary,
        "metrics": {
            "fixed_ratio_pct": round((summary["fixed_costs"] / summary["total_income"]) * 100, 1),
            "debt_ratio_pct": round((summary["debts_total"] / summary["total_income"]) * 100, 1),
            "surplus_ratio_pct": round((summary["net_surplus"] / summary["total_income"]) * 100, 1),
            "vr_benefit": 500.00,
            "liberty_horizon_month": "Abril 2027",
            "months_to_liberty": 7
        }
    }


@app.get("/api/timeline")
async def get_timeline():
    """Retorna o fluxo de caixa projetado mês a mês (Outubro a Agosto)."""
    timeline = await db_manager.get_timeline()
    return [item.model_dump() for item in timeline]


@app.get("/api/consensus")
async def get_consensus(month: str = "Outubro"):
    """Retorna a decisão orçamentária do comitê de IA (via cache ou execução)."""
    summary = await db_manager.get_financial_summary(month)
    result = await consensus_engine.run_consensus_loop(summary, force_recalculate=False)
    return result.model_dump()


@app.post("/api/consensus/recalculate")
@limiter.limit(os.getenv("RATE_LIMIT_RECALCULATE", "3/hour"))
async def recalculate_consensus(request: Request, month: str = "Outubro"):
    """
    Força a reexecução do loop de consenso multi-IA.
    Limitado a 3 requisições por hora por IP para proteção estrita de cotas gratuitas.
    """
    summary = await db_manager.get_financial_summary(month)
    result = await consensus_engine.run_consensus_loop(summary, force_recalculate=True)
    return result.model_dump()


@app.post("/api/questionnaire")
async def update_questionnaire(data: QuestionnaireInput):
    """
    Atualiza as variáveis orçamentárias pelo questionário interativo.
    Invalida automaticamente o cache de consenso do Postgres.
    """
    update_dict = data.model_dump(exclude_none=True)
    await db_manager.update_financial_inputs(update_dict)
    
    # Recalcular resumo do mês atual
    summary = await db_manager.get_financial_summary("Outubro")
    return {
        "status": "success",
        "message": "Dados financeiros atualizados com sucesso e cache invalidado.",
        "updated_summary": summary
    }


@app.post("/api/methodology")
async def calculate_methodology(req: MethodologyRequest):
    """
    Calcula as cotas de alocação de acordo com o seletor de metodologias:
    - 50-30-20
    - 60-20-20
    - 70-20-10
    - Base Zero
    """
    summary = await db_manager.get_financial_summary("Outubro")
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
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
