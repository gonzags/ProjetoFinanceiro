"""
utils.py - Módulo de Banco de Dados, Cálculos Financeiros e Cache (Ledger Horizon)
Suporte para PostgreSQL 16 (asyncpg) com fallback automático para DemoDataManager em memória.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
from pydantic import BaseModel, Field

logger = logging.getLogger("ledger_horizon.utils")

# -----------------------------------------------------------------------------
# Modelos de Dados Pydantic
# -----------------------------------------------------------------------------

class UserRecord(BaseModel):
    id: int
    email: str
    password_hash: Optional[str] = None
    name: str
    auth_provider: str = "local"
    google_sub: Optional[str] = None
    onboarding_completed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AllocationSchema(BaseModel):
    necessidades: float = Field(..., description="Percentual para necessidades (0.0 a 1.0 ou 0 a 100)")
    desejos: float = Field(..., description="Percentual para desejos (0.0 a 1.0 ou 0 a 100)")
    futuro: float = Field(..., description="Percentual para futuro/dívidas/investimentos")


class ConsensusRecord(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    created_at: datetime
    allocation: Dict[str, float]
    confidence_score: float
    risk_flags: List[str]
    reasoning_summary: str
    consensus_status: str  # "total", "parcial", "deterministico_local"
    provider_metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class FinancialProfile(BaseModel):
    user_name: str
    salary_gross: float = 2342.46
    salary_net: float = 1843.42
    benefits_vr: float = 500.00
    september_balance: float = 326.45
    september_due: float = 163.37
    receivables: List[Dict[str, Any]] = Field(default_factory=list)


class FixedExpense(BaseModel):
    name: str
    amount: float
    category: str


class MonthlyCashFlow(BaseModel):
    month: str
    total_income: float
    fixed_costs: float
    debts_total: float
    picpay_amount: float
    nubank_amount: float
    special_events: float
    total_outflow: float
    net_surplus: float
    status_label: str


class FinancialGoal(BaseModel):
    id: Optional[int] = None
    user_id: int
    title: str
    goal_type: str  # emergencia, imovel, aposentadoria, viagem, divida, independencia, outro
    target_amount: Optional[float] = None
    target_date: Optional[date] = None
    current_amount: float = 0.0
    monthly_contribution: float = 0.0
    priority: int = 1
    is_active: bool = True
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ExpenseCategory(BaseModel):
    id: Optional[int] = None
    user_id: int
    name: str
    category: str
    icon: Optional[str] = None
    color: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0

class ExpenseEntry(BaseModel):
    id: Optional[int] = None
    user_id: int
    budget_month_id: int
    category_id: Optional[int] = None
    description: str
    amount: float
    expense_type: str = 'fixed'  # fixed, variable, debt, card
    due_date: Optional[date] = None
    is_paid: bool = False
    paid_at: Optional[date] = None
    installment_current: Optional[int] = None
    installment_total: Optional[int] = None
    notes: Optional[str] = None

class IncomeEntry(BaseModel):
    id: Optional[int] = None
    user_id: int
    budget_month_id: int
    description: str
    amount: float
    income_type: str = 'salary'  # salary, extra, benefit, investment_return, other
    is_received: bool = False
    received_at: Optional[date] = None
    notes: Optional[str] = None

class BudgetMonth(BaseModel):
    id: Optional[int] = None
    user_id: int
    year: int
    month: int
    label: Optional[str] = None
    is_closed: bool = False
    notes: Optional[str] = None

class MonthlySnapshot(BaseModel):
    year: int
    month: int
    label: str
    total_income: float
    total_expenses_fixed: float
    total_expenses_variable: float
    total_expenses_debt: float
    total_expenses_card: float
    total_outflow: float
    net_surplus: float
    is_closed: bool
    status_label: str

class InvestmentPortfolio(BaseModel):
    id: Optional[int] = None
    user_id: int
    consensus_record_id: Optional[int] = None
    generated_at: Optional[datetime] = None
    is_active: bool = True
    pct_renda_fixa: float = 0.0
    pct_tesouro: float = 0.0
    pct_fiis: float = 0.0
    pct_acoes: float = 0.0
    pct_reserva_liquida: float = 0.0
    pct_cripto: float = 0.0
    monthly_investment_target: float = 0.0
    emergency_reserve_target: float = 0.0
    months_to_goal: Optional[int] = None
    projection_json: Optional[Dict[str, Any]] = None
    rationale: Optional[str] = None


# -----------------------------------------------------------------------------
# Carregamento de Seed Data Seguro (Proteção contra exposição no Git)
# -----------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

def load_seed_data() -> Dict[str, Any]:
    """
    Carrega seed_data.json se existir localmente (gitignored).
    Caso contrário, carrega seed_data.example.json com segurança.
    """
    seed_file = BASE_DIR / "seed_data.json"
    if not seed_file.exists():
        seed_file = BASE_DIR / "seed_data.example.json"
    
    if seed_file.exists():
        try:
            with open(seed_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao ler arquivo de seed {seed_file}: {e}")
            
    # Fallback seguro com os dados do histórico
    return {
        "profile": {
            "user_name": "Pedro Silva",
            "salary_gross": 2342.46,
            "salary_net": 1843.42,
            "benefits_vr": 500.00,
            "september_balance": 326.45,
            "september_due": 163.37,
            "receivables": [
                {"name": "Parcela 110", "amount": 110.00, "months": ["Outubro", "Novembro", "Dezembro", "Janeiro"]},
                {"name": "Parcela 180", "amount": 180.00, "months": ["Outubro", "Novembro", "Dezembro", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho"]}
            ]
        },
        "fixed_expenses": [
            {"name": "Academia", "amount": 164.50, "category": "Saúde"},
            {"name": "Internet Residencial", "amount": 60.00, "category": "Conectividade"},
            {"name": "Internet Móvel", "amount": 45.00, "category": "Conectividade"},
            {"name": "Spotify", "amount": 11.00, "category": "Assinaturas"},
            {"name": "Armazenamento Google", "amount": 4.50, "category": "Assinaturas"}
        ],
        "card_schedules": {
            "PicPay": {
                "closing_day": 27,
                "installments": {
                    "Outubro": 539.00, "Novembro": 469.39, "Dezembro": 373.68, "Janeiro": 344.63,
                    "Fevereiro": 217.33, "Março": 217.33, "Abril": 99.21, "Maio": 99.21, "Junho": 99.21,
                    "Julho": 0.0, "Agosto": 0.0
                }
            },
            "Nubank": {
                "closing_day": 4,
                "installments": {
                    "Outubro": 697.83, "Novembro": 557.70, "Dezembro": 447.91, "Janeiro": 396.37,
                    "Fevereiro": 396.37, "Março": 297.25, "Abril": 37.05, "Maio": 37.05, "Junho": 37.05,
                    "Julho": 37.05, "Agosto": 37.05
                }
            }
        },
        "one_off_commitments": [
            {"name": "Viagem", "amount": 500.00, "month": "Outubro"}
        ]
    }


# -----------------------------------------------------------------------------
# Motor Determinístico Local (Fallback sem IA - claudeaudita.pdf seção 2.5)
# -----------------------------------------------------------------------------

def compute_deterministic_local_allocation(financial_summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cálculo determinístico local baseado em regras matemáticas e dados orçamentários.
    Garante que a plataforma nunca dependa de rede externa para responder.
    """
    income = financial_summary.get("total_income", 2133.42)
    fixed = financial_summary.get("fixed_costs", 285.00)
    debts = financial_summary.get("debts_total", 1236.83)
    special = financial_summary.get("special_events", 500.00)

    # Cálculo das cotas reais para o mês atual
    # Necessidades: Custos fixos + margem básica
    necessidades_pct = round((fixed / income) * 100, 1)
    # Futuro/Dívidas: Dívidas do mês
    futuro_pct = round(((debts) / income) * 100, 1)
    # Desejos: Lazer + Eventos especiais ou sobra
    desejos_pct = round(max(0.0, 100.0 - necessidades_pct - futuro_pct), 1)

    # Normalização se estourar 100%
    soma = necessidades_pct + desejos_pct + futuro_pct
    if soma > 100.0:
        fator = 100.0 / soma
        necessidades_pct = round(necessidades_pct * fator, 1)
        desejos_pct = round(desejos_pct * fator, 1)
        futuro_pct = round(100.0 - necessidades_pct - desejos_pct, 1)

    risk_flags = []
    if debts / income > 0.50:
        risk_flags.append("Dívidas comprometem mais de 50% da renda líquida neste período.")
    if special > 0:
        risk_flags.append(f"Gasto extraordinário de R$ {special:.2f} registrado para o mês.")
    if not risk_flags:
        risk_flags.append("Equilíbrio orçamentário dentro dos parâmetros de estabilidade.")

    summary = (
        f"Alocação calculada pelo motor determinístico local: {necessidades_pct}% necessidades, "
        f"{desejos_pct}% desejos e {futuro_pct}% futuro/dívidas. Sobra líquida estimada em conformidade."
    )[:300]

    return {
        "allocation": {
            "necessidades": necessidades_pct,
            "desejos": desejos_pct,
            "futuro": futuro_pct
        },
        "confidence_score": 0.85,
        "risk_flags": risk_flags,
        "reasoning_summary": summary,
        "consensus_status": "deterministico_local",
        "provider_metadata": {"engine": "local_rules_v4", "timestamp": datetime.now(timezone.utc).isoformat()}
    }


# -----------------------------------------------------------------------------
# Gerenciador em Memória para Desenvolvimento / Demonstração (Multi-Tenant)
# -----------------------------------------------------------------------------

class DemoDataManager:
    """Armazena e manipula os dados em memória quando o PostgreSQL não estiver disponível."""
    
    def __init__(self):
        self.seed = load_seed_data()
        self.cached_consensus: Optional[ConsensusRecord] = None
        # Estruturas multi-tenant em memória
        self.users: Dict[int, Dict[str, Any]] = {}
        self.user_by_email: Dict[str, int] = {}
        self.user_by_google: Dict[str, int] = {}
        self.next_user_id: int = 1
        self.user_profiles: Dict[int, Dict[str, Any]] = {}
        self.cached_consensus_by_user: Dict[Optional[int], ConsensusRecord] = {}
        self._init_default_cache()

    def _init_default_cache(self):
        summary = self.get_financial_summary("Outubro")
        res = compute_deterministic_local_allocation(summary)
        self.cached_consensus = ConsensusRecord(
            id=1,
            user_id=None,
            created_at=datetime.now(timezone.utc),
            allocation=res["allocation"],
            confidence_score=res["confidence_score"],
            risk_flags=res["risk_flags"],
            reasoning_summary=res["reasoning_summary"],
            consensus_status=res["consensus_status"],
            provider_metadata=res["provider_metadata"],
            is_active=True
        )

    def create_user(
        self,
        email: str,
        password_hash: Optional[str],
        name: str,
        auth_provider: str = "local",
        google_sub: Optional[str] = None
    ) -> Dict[str, Any]:
        email_clean = email.lower().strip()
        if email_clean in self.user_by_email:
            raise ValueError("E-mail já cadastrado.")
        if google_sub and google_sub in self.user_by_google:
            raise ValueError("Conta Google já vinculada.")

        uid = self.next_user_id
        self.next_user_id += 1
        user_dict = {
            "id": uid,
            "email": email_clean,
            "password_hash": password_hash,
            "name": name.strip(),
            "auth_provider": auth_provider,
            "google_sub": google_sub,
            "onboarding_completed": False,
            "created_at": datetime.now(timezone.utc)
        }
        self.users[uid] = user_dict
        self.user_by_email[email_clean] = uid
        if google_sub:
            self.user_by_google[google_sub] = uid
        return user_dict

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        return self.users.get(user_id)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        uid = self.user_by_email.get(email.lower().strip())
        return self.users.get(uid) if uid else None

    def get_user_by_google_sub(self, google_sub: str) -> Optional[Dict[str, Any]]:
        uid = self.user_by_google.get(google_sub)
        return self.users.get(uid) if uid else None

    def _normalize_onboarding_payload(self, user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        if "monthly_income" in payload or "fixed_expenses_val" in payload:
            user = self.users.get(user_id, {})
            u_name = payload.get("name") or user.get("name", "Usuário")
            fixed_val = float(payload.get("fixed_expenses_val") or 0.0)
            variable_val = float(payload.get("variable_expenses_val") or 0.0)
            salary_net = float(payload.get("monthly_income") or 0.0)
            extra_val = float(payload.get("extra_income") or 0.0)
            
            return {
                "profile": {
                    "user_name": u_name,
                    "age": payload.get("age"),
                    "occupation": payload.get("occupation"),
                    "salary_net": salary_net,
                    "benefits_vr": extra_val,
                    "saved_amount": float(payload.get("saved_amount") or 0.0),
                    "saved_destination": payload.get("saved_destination", ""),
                    "invests": payload.get("invests", ""),
                    "investment_types": payload.get("investment_types", []),
                    "risk_tolerance": payload.get("risk_tolerance", "moderado"),
                    "receivables": []
                },
                "fixed_expenses": [
                    {"name": "Despesas Fixas", "amount": fixed_val, "category": "Essencial"}
                ],
                "card_schedules": {},
                "one_off_commitments": [
                    {"name": "Gastos Variáveis", "amount": variable_val, "month": "Outubro"}
                ],
                "onboarding_answers": payload
            }
        return payload

    def set_onboarding_completed(self, user_id: int, completed: bool = True):
        if user_id in self.users:
            self.users[user_id]["onboarding_completed"] = completed

    def save_onboarding_profile(self, user_id: int, payload: Dict[str, Any], is_draft: bool = False):
        normalized = self._normalize_onboarding_payload(user_id, payload)
        self.user_profiles[user_id] = normalized
        if not is_draft:
            self.set_onboarding_completed(user_id, True)
            self.invalidate_cache(user_id=user_id)

    def get_onboarding_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        prof = self.user_profiles.get(user_id)
        if prof and "onboarding_answers" in prof:
            return prof["onboarding_answers"]
        return prof

    def get_financial_summary(self, month: str = "Outubro", user_id: Optional[int] = None) -> Dict[str, Any]:
        data_source = self.user_profiles.get(user_id, self.seed) if user_id else self.seed
        profile = data_source.get("profile", {})
        salary_net = float(profile.get("salary_net", 0.0))
        
        # Somar recebíveis do mês
        receivables_month = sum(
            r.get("amount", 0.0) for r in profile.get("receivables", [])
            if month in r.get("months", [])
        )
        total_income = salary_net + receivables_month

        # Somar custos fixos
        fixed_costs = sum(item.get("amount", 0.0) for item in data_source.get("fixed_expenses", []))

        # Somar faturas
        cards = data_source.get("card_schedules", {})
        picpay_amount = float(cards.get("PicPay", {}).get("installments", {}).get(month, 0.0))
        nubank_amount = float(cards.get("Nubank", {}).get("installments", {}).get(month, 0.0))

        # Compromissos pontuais
        special = sum(
            item.get("amount", 0.0) for item in data_source.get("one_off_commitments", [])
            if item.get("month") == month
        )

        debts_total = picpay_amount + nubank_amount
        total_outflow = fixed_costs + debts_total + special
        net_surplus = total_income - total_outflow

        return {
            "month": month,
            "total_income": round(total_income, 2),
            "salary_net": round(salary_net, 2),
            "receivables": round(receivables_month, 2),
            "fixed_costs": round(fixed_costs, 2),
            "debts_total": round(debts_total, 2),
            "picpay_amount": round(picpay_amount, 2),
            "nubank_amount": round(nubank_amount, 2),
            "special_events": round(special, 2),
            "total_outflow": round(total_outflow, 2),
            "net_surplus": round(net_surplus, 2),
        }

    def get_timeline(self, user_id: Optional[int] = None) -> List[MonthlyCashFlow]:
        months = ["Outubro", "Novembro", "Dezembro", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto"]
        timeline = []
        for m in months:
            summary = self.get_financial_summary(m, user_id=user_id)
            
            # Status label
            if m == "Outubro":
                lbl = "Zona Crítica (Viagem + Cartões)"
            elif m in ["Novembro", "Dezembro"]:
                lbl = "Início do Alívio / Reserva"
            elif m in ["Janeiro", "Fevereiro", "Março"]:
                lbl = "Estabilidade e Aceleração"
            else:
                lbl = "Liberdade Financeira (80% Livre)"

            timeline.append(MonthlyCashFlow(
                month=m,
                total_income=summary["total_income"],
                fixed_costs=summary["fixed_costs"],
                debts_total=summary["debts_total"],
                picpay_amount=summary["picpay_amount"],
                nubank_amount=summary["nubank_amount"],
                special_events=summary["special_events"],
                total_outflow=summary["total_outflow"],
                net_surplus=summary["net_surplus"],
                status_label=lbl
            ))
        return timeline

    def get_active_cache(self, max_age_hours: int = 24, user_id: Optional[int] = None) -> Optional[ConsensusRecord]:
        cached = self.cached_consensus_by_user.get(user_id) if user_id is not None else self.cached_consensus
        if not cached or not cached.is_active:
            return None
        
        now = datetime.now(timezone.utc)
        age = (now - cached.created_at).total_seconds() / 3600.0
        if age > max_age_hours:
            logger.info(f"Cache expirado por idade (>24h) para user_id={user_id}.")
            return None
        return cached

    def save_cache(self, consensus_data: Dict[str, Any], user_id: Optional[int] = None) -> ConsensusRecord:
        rec = ConsensusRecord(
            id=1,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            allocation=consensus_data["allocation"],
            confidence_score=consensus_data["confidence_score"],
            risk_flags=consensus_data["risk_flags"],
            reasoning_summary=consensus_data["reasoning_summary"],
            consensus_status=consensus_data.get("consensus_status", "total"),
            provider_metadata=consensus_data.get("provider_metadata", {}),
            is_active=True
        )
        if user_id is not None:
            self.cached_consensus_by_user[user_id] = rec
        else:
            self.cached_consensus = rec
        return rec

    def invalidate_cache(self, user_id: Optional[int] = None):
        if user_id is not None and user_id in self.cached_consensus_by_user:
            self.cached_consensus_by_user[user_id].is_active = False
            logger.info(f"Cache de consenso invalidado para user_id={user_id}.")
        elif user_id is None and self.cached_consensus:
            self.cached_consensus.is_active = False
            logger.info("Cache de consenso global invalidado.")

    def update_financial_inputs(self, new_data: Dict[str, Any], user_id: Optional[int] = None):
        """Atualiza valores via questionário e invalida o cache."""
        target = self.user_profiles.get(user_id, self.seed) if user_id else self.seed
        profile = target.setdefault("profile", {})
        if "salary_net" in new_data:
            profile["salary_net"] = float(new_data["salary_net"])
        if "fixed_expenses" in new_data:
            target["fixed_expenses"] = new_data["fixed_expenses"]
        if "card_schedules" in new_data:
            schedules = target.setdefault("card_schedules", {})
            for card_name, card_info in new_data["card_schedules"].items():
                if card_name in schedules:
                    schedules[card_name].setdefault("installments", {}).update(card_info.get("installments", {}))
                else:
                    schedules[card_name] = card_info
        if "one_off_commitments" in new_data:
            target["one_off_commitments"] = new_data["one_off_commitments"]
            
        self.invalidate_cache(user_id=user_id)


# -----------------------------------------------------------------------------
# Gerenciador com PostgreSQL 16 (asyncpg com queries parametrizadas)
# -----------------------------------------------------------------------------

class DatabaseManager:
    """Gerenciador principal que usa PostgreSQL ou faz fallback transparente para DemoDataManager."""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.demo_manager = DemoDataManager()
        self.is_connected = False

    async def connect(self):
        """Tenta conectar ao PostgreSQL usando variáveis de ambiente."""
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = int(os.getenv("POSTGRES_PORT", 5432))
        database = os.getenv("POSTGRES_DB", "main_db")
        user = os.getenv("POSTGRES_USER", "usr_pedro")
        password = os.getenv("POSTGRES_PASSWORD", "P13m04a23c13*")

        try:
            self.pool = await asyncpg.create_pool(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                min_size=1,
                max_size=5,
                timeout=3.0,
                command_timeout=5.0
            )
            self.is_connected = True
            logger.info("Conexão com PostgreSQL estabelecida com sucesso.")
            await self._init_tables()
        except Exception as e:
            logger.warning(
                f"PostgreSQL não acessível em {host}:{port} ({e}). "
                f"Ativando 'Modo demonstração — dados em cache local'."
            )
            self.is_connected = False

    async def _init_tables(self):
        """Cria as tabelas necessárias no PostgreSQL com queries parametrizadas."""
        if not self.pool:
            return

        queries = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash TEXT,
                name VARCHAR(255) NOT NULL,
                auth_provider VARCHAR(50) DEFAULT 'local',
                google_sub VARCHAR(255) UNIQUE,
                onboarding_completed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS user_financial_profiles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS llm_consensus_cache (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                allocation JSONB NOT NULL,
                confidence_score NUMERIC(5, 2) NOT NULL,
                risk_flags JSONB NOT NULL,
                reasoning_summary TEXT NOT NULL,
                consensus_status VARCHAR(50) NOT NULL,
                provider_metadata JSONB DEFAULT '{}'::jsonb,
                is_active BOOLEAN NOT NULL DEFAULT TRUE
            );
            """,
            """
            ALTER TABLE llm_consensus_cache ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;
            """,
            # Bloco 1: expandir users
            """
            ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
            """,
            # Bloco 2: expandir user_financial_profiles com colunas tipadas
            """
            ALTER TABLE user_financial_profiles
                ADD COLUMN IF NOT EXISTS full_name            VARCHAR(255),
                ADD COLUMN IF NOT EXISTS age                  INTEGER,
                ADD COLUMN IF NOT EXISTS occupation           VARCHAR(255),
                ADD COLUMN IF NOT EXISTS city                 VARCHAR(255),
                ADD COLUMN IF NOT EXISTS monthly_income_net   NUMERIC(12,2) DEFAULT 0,
                ADD COLUMN IF NOT EXISTS monthly_income_gross NUMERIC(12,2) DEFAULT 0,
                ADD COLUMN IF NOT EXISTS extra_income         NUMERIC(12,2) DEFAULT 0,
                ADD COLUMN IF NOT EXISTS benefits_vr          NUMERIC(12,2) DEFAULT 0,
                ADD COLUMN IF NOT EXISTS saved_amount         NUMERIC(12,2) DEFAULT 0,
                ADD COLUMN IF NOT EXISTS saved_destination    VARCHAR(255),
                ADD COLUMN IF NOT EXISTS invests              VARCHAR(30),
                ADD COLUMN IF NOT EXISTS investment_types     TEXT[],
                ADD COLUMN IF NOT EXISTS risk_tolerance       VARCHAR(20),
                ADD COLUMN IF NOT EXISTS data_consent_given   BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS data_consent_at      TIMESTAMPTZ;
            """,
            # Bloco 3: objetivos
            """
            CREATE TABLE IF NOT EXISTS financial_goals (
                id                   SERIAL PRIMARY KEY,
                user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title                VARCHAR(255) NOT NULL,
                goal_type            VARCHAR(30) NOT NULL,
                target_amount        NUMERIC(12,2),
                target_date          DATE,
                current_amount       NUMERIC(12,2) NOT NULL DEFAULT 0,
                monthly_contribution NUMERIC(12,2) NOT NULL DEFAULT 0,
                priority             INTEGER NOT NULL DEFAULT 1,
                is_active            BOOLEAN NOT NULL DEFAULT TRUE,
                notes                TEXT,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """,
            # Bloco 4: categorias de despesa
            """
            CREATE TABLE IF NOT EXISTS expense_categories (
                id          SERIAL PRIMARY KEY,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name        VARCHAR(100) NOT NULL,
                category    VARCHAR(50) NOT NULL,
                icon        VARCHAR(10),
                color       VARCHAR(7),
                is_active   BOOLEAN NOT NULL DEFAULT TRUE,
                sort_order  INTEGER DEFAULT 0,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (user_id, name)
            );
            """,
            # Bloco 5: períodos mensais
            """
            CREATE TABLE IF NOT EXISTS budget_months (
                id          SERIAL PRIMARY KEY,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                year        INTEGER NOT NULL,
                month       INTEGER NOT NULL,
                label       VARCHAR(20),
                is_closed   BOOLEAN NOT NULL DEFAULT FALSE,
                notes       TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (user_id, year, month)
            );
            """,
            # Bloco 6: despesas
            """
            CREATE TABLE IF NOT EXISTS expense_entries (
                id              SERIAL PRIMARY KEY,
                user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                budget_month_id INTEGER NOT NULL REFERENCES budget_months(id) ON DELETE CASCADE,
                category_id     INTEGER REFERENCES expense_categories(id) ON DELETE SET NULL,
                description     VARCHAR(255) NOT NULL,
                amount          NUMERIC(12,2) NOT NULL,
                expense_type    VARCHAR(20) NOT NULL DEFAULT 'fixed',
                due_date        DATE,
                is_paid         BOOLEAN NOT NULL DEFAULT FALSE,
                paid_at         DATE,
                installment_current INTEGER,
                installment_total   INTEGER,
                notes           TEXT,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """,
            # Bloco 7: receitas
            """
            CREATE TABLE IF NOT EXISTS income_entries (
                id              SERIAL PRIMARY KEY,
                user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                budget_month_id INTEGER NOT NULL REFERENCES budget_months(id) ON DELETE CASCADE,
                description     VARCHAR(255) NOT NULL,
                amount          NUMERIC(12,2) NOT NULL,
                income_type     VARCHAR(20) NOT NULL DEFAULT 'salary',
                is_received     BOOLEAN NOT NULL DEFAULT FALSE,
                received_at     DATE,
                notes           TEXT,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """,
            # Bloco 8: portfólio de investimentos
            """
            CREATE TABLE IF NOT EXISTS investment_portfolios (
                id                        SERIAL PRIMARY KEY,
                user_id                   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                consensus_record_id       INTEGER REFERENCES llm_consensus_cache(id) ON DELETE SET NULL,
                generated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                is_active                 BOOLEAN NOT NULL DEFAULT TRUE,
                pct_renda_fixa            NUMERIC(5,2) NOT NULL DEFAULT 0,
                pct_tesouro               NUMERIC(5,2) NOT NULL DEFAULT 0,
                pct_fiis                  NUMERIC(5,2) NOT NULL DEFAULT 0,
                pct_acoes                 NUMERIC(5,2) NOT NULL DEFAULT 0,
                pct_reserva_liquida       NUMERIC(5,2) NOT NULL DEFAULT 0,
                pct_cripto                NUMERIC(5,2) NOT NULL DEFAULT 0,
                monthly_investment_target NUMERIC(12,2) DEFAULT 0,
                emergency_reserve_target  NUMERIC(12,2) DEFAULT 0,
                months_to_goal            INTEGER,
                projection_json           JSONB,
                rationale                 TEXT
            );
            """,
            # Bloco 9: respostas individuais de LLM
            """
            CREATE TABLE IF NOT EXISTS llm_individual_responses (
                id              SERIAL PRIMARY KEY,
                consensus_id    INTEGER NOT NULL REFERENCES llm_consensus_cache(id) ON DELETE CASCADE,
                user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider_name   VARCHAR(50) NOT NULL,
                round_number    INTEGER NOT NULL DEFAULT 1,
                raw_response    JSONB NOT NULL,
                allocation      JSONB,
                confidence      NUMERIC(4,3),
                risk_flags      TEXT[],
                reasoning       TEXT,
                responded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        ]
        
        async with self.pool.acquire() as conn:
            for q in queries:
                try:
                    await conn.execute(q)
                except Exception as e:
                    logger.warning(f"Erro ao executar DDL ({e}).")
            logger.info("Schema completo verificado/criado: 9 tabelas + extensões.")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self.is_connected = False
            logger.info("Pool PostgreSQL encerrado.")

    def get_display_name(self, user_id: Optional[int] = None) -> str:
        """Retorna o nome do usuário a partir da fonte única de dados."""
        if user_id is not None:
            user = self.demo_manager.get_user_by_id(user_id)
            if user:
                return user["name"]
        return self.demo_manager.seed.get("profile", {}).get(
            "user_name", os.getenv("USER_DISPLAY_NAME", "Pedro Silva")
        )

    def get_connection_status(self) -> str:
        """Retorna estado do badge de conexão."""
        if self.is_connected:
            return "Data Warehouse: PostgreSQL 16 (Connected)"
        return "Modo demonstração — dados em cache local"

    # -------------------------------------------------------------------------
    # Operações de Usuário (Multi-Tenant)
    # -------------------------------------------------------------------------
    async def create_user(
        self,
        email: str,
        password_hash: Optional[str],
        name: str,
        auth_provider: str = "local",
        google_sub: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.is_connected or not self.pool:
            return self.demo_manager.create_user(email, password_hash, name, auth_provider, google_sub)

        email_clean = email.lower().strip()
        query = """
        INSERT INTO users (email, password_hash, name, auth_provider, google_sub, onboarding_completed, created_at)
        VALUES ($1, $2, $3, $4, $5, FALSE, NOW())
        RETURNING id, email, password_hash, name, auth_provider, google_sub, onboarding_completed, created_at;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, email_clean, password_hash, name.strip(), auth_provider, google_sub)
            return dict(row)

    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected or not self.pool:
            return self.demo_manager.get_user_by_id(user_id)

        query = "SELECT * FROM users WHERE id = $1 LIMIT 1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)
            return dict(row) if row else None

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        if not self.is_connected or not self.pool:
            return self.demo_manager.get_user_by_email(email)

        query = "SELECT * FROM users WHERE email = $1 LIMIT 1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, email.lower().strip())
            return dict(row) if row else None

    async def get_user_by_google_sub(self, google_sub: str) -> Optional[Dict[str, Any]]:
        if not self.is_connected or not self.pool:
            return self.demo_manager.get_user_by_google_sub(google_sub)

        query = "SELECT * FROM users WHERE google_sub = $1 LIMIT 1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, google_sub)
            return dict(row) if row else None

    async def set_onboarding_completed(self, user_id: int, completed: bool = True):
        self.demo_manager.set_onboarding_completed(user_id, completed)
        if self.is_connected and self.pool:
            query = "UPDATE users SET onboarding_completed = $1 WHERE id = $2;"
            async with self.pool.acquire() as conn:
                await conn.execute(query, completed, user_id)

    async def save_onboarding_profile(self, user_id: int, payload: Dict[str, Any], is_draft: bool = False):
        self.demo_manager.save_onboarding_profile(user_id, payload, is_draft=is_draft)
        normalized = self.demo_manager.user_profiles.get(user_id, payload)
        if self.is_connected and self.pool:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    upsert_query = """
                    INSERT INTO user_financial_profiles (user_id, payload, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW();
                    """
                    await conn.execute(upsert_query, user_id, json.dumps(normalized))
                    
                    # Upsert colunas tipadas e consentimento
                    typedcols_query = """
                    UPDATE user_financial_profiles SET
                        full_name          = $2,
                        age                = $3,
                        occupation         = $4,
                        monthly_income_net = $5,
                        extra_income       = $6,
                        saved_amount       = $7,
                        saved_destination  = $8,
                        invests            = $9,
                        investment_types   = $10,
                        risk_tolerance     = $11,
                        data_consent_given = $12,
                        data_consent_at    = CASE WHEN $12 THEN NOW() ELSE data_consent_at END,
                        updated_at         = NOW()
                    WHERE user_id = $1;
                    """
                    onb = payload  # payload original do onboarding
                    await conn.execute(
                        typedcols_query,
                        user_id,
                        onb.get('name') or onb.get('user_name'),
                        int(onb.get('age')) if onb.get('age') else None,
                        onb.get('occupation'),
                        float(onb.get('monthly_income') or 0),
                        float(onb.get('extra_income') or 0),
                        float(onb.get('saved_amount') or 0),
                        onb.get('saved_destination'),
                        onb.get('invests'),
                        onb.get('investment_types') or [],
                        onb.get('risk_tolerance') or 'moderado',
                        bool(onb.get('data_consent', False))
                    )
                    
                    if not is_draft:
                        await conn.execute("UPDATE users SET onboarding_completed = TRUE WHERE id = $1;", user_id)
                        await conn.execute("UPDATE llm_consensus_cache SET is_active = FALSE WHERE user_id = $1;", user_id)

    async def get_onboarding_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected or not self.pool:
            return self.demo_manager.get_onboarding_profile(user_id)
        query = "SELECT payload FROM user_financial_profiles WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)
            if row:
                raw = row["payload"]
                prof = json.loads(raw) if isinstance(raw, str) else raw
                self.demo_manager.user_profiles[user_id] = prof
                if isinstance(prof, dict) and "onboarding_answers" in prof:
                    return prof["onboarding_answers"]
                return prof
        return self.demo_manager.get_onboarding_profile(user_id)

    async def _ensure_user_profile_loaded(self, user_id: Optional[int]):
        """Garante que o perfil do usuário seja carregado do PostgreSQL para a memória deste processo/worker."""
        if not self.is_connected or not self.pool or user_id is None:
            return
        query = "SELECT payload FROM user_financial_profiles WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)
            if row:
                payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
                self.demo_manager.user_profiles[user_id] = payload

    async def get_financial_summary(self, month: str = "Outubro", user_id: Optional[int] = None) -> Dict[str, Any]:
        await self._ensure_user_profile_loaded(user_id)
        return self.demo_manager.get_financial_summary(month, user_id=user_id)

    async def get_timeline(self, user_id: Optional[int] = None) -> List[MonthlyCashFlow]:
        await self._ensure_user_profile_loaded(user_id)
        return self.demo_manager.get_timeline(user_id=user_id)

    async def get_active_cache(self, max_age_hours: int = 24, user_id: Optional[int] = None) -> Optional[ConsensusRecord]:
        if not self.is_connected or not self.pool:
            return self.demo_manager.get_active_cache(max_age_hours, user_id=user_id)

        if user_id is not None:
            query = """
            SELECT id, user_id, created_at, allocation, confidence_score, risk_flags, reasoning_summary, 
                   consensus_status, provider_metadata, is_active
            FROM llm_consensus_cache
            WHERE is_active = TRUE 
              AND user_id = $1
              AND created_at >= NOW() - INTERVAL '1 hour' * $2
            ORDER BY created_at DESC
            LIMIT 1;
            """
            params = [user_id, max_age_hours]
        else:
            query = """
            SELECT id, user_id, created_at, allocation, confidence_score, risk_flags, reasoning_summary, 
                   consensus_status, provider_metadata, is_active
            FROM llm_consensus_cache
            WHERE is_active = TRUE 
              AND user_id IS NULL
              AND created_at >= NOW() - INTERVAL '1 hour' * $1
            ORDER BY created_at DESC
            LIMIT 1;
            """
            params = [max_age_hours]

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, *params)
                if row:
                    return ConsensusRecord(
                        id=row["id"],
                        user_id=row["user_id"],
                        created_at=row["created_at"],
                        allocation=json.loads(row["allocation"]) if isinstance(row["allocation"], str) else row["allocation"],
                        confidence_score=float(row["confidence_score"]),
                        risk_flags=json.loads(row["risk_flags"]) if isinstance(row["risk_flags"], str) else row["risk_flags"],
                        reasoning_summary=row["reasoning_summary"],
                        consensus_status=row["consensus_status"],
                        provider_metadata=json.loads(row["provider_metadata"]) if isinstance(row["provider_metadata"], str) else (row["provider_metadata"] or {}),
                        is_active=row["is_active"]
                    )
        except Exception as e:
            logger.error(f"Erro ao consultar cache no PostgreSQL: {e}")

        return self.demo_manager.get_active_cache(max_age_hours, user_id=user_id)

    async def save_cache(self, consensus_data: Dict[str, Any], user_id: Optional[int] = None) -> ConsensusRecord:
        if not self.is_connected or not self.pool:
            return self.demo_manager.save_cache(consensus_data, user_id=user_id)

        if user_id is not None:
            invalidate_query = "UPDATE llm_consensus_cache SET is_active = FALSE WHERE is_active = TRUE AND user_id = $1;"
            inv_params = [user_id]
        else:
            invalidate_query = "UPDATE llm_consensus_cache SET is_active = FALSE WHERE is_active = TRUE AND user_id IS NULL;"
            inv_params = []

        insert_query = """
        INSERT INTO llm_consensus_cache (
            user_id, created_at, allocation, confidence_score, risk_flags, reasoning_summary, 
            consensus_status, provider_metadata, is_active
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, TRUE)
        RETURNING id, created_at;
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(invalidate_query, *inv_params)
                    now = datetime.now(timezone.utc)
                    row = await conn.fetchrow(
                        insert_query,
                        user_id,
                        now,
                        json.dumps(consensus_data["allocation"]),
                        float(consensus_data["confidence_score"]),
                        json.dumps(consensus_data["risk_flags"]),
                        consensus_data["reasoning_summary"],
                        consensus_data.get("consensus_status", "total"),
                        json.dumps(consensus_data.get("provider_metadata", {}))
                    )
                    return ConsensusRecord(
                        id=row["id"],
                        user_id=user_id,
                        created_at=row["created_at"],
                        allocation=consensus_data["allocation"],
                        confidence_score=consensus_data["confidence_score"],
                        risk_flags=consensus_data["risk_flags"],
                        reasoning_summary=consensus_data["reasoning_summary"],
                        consensus_status=consensus_data.get("consensus_status", "total"),
                        provider_metadata=consensus_data.get("provider_metadata", {}),
                        is_active=True
                    )
        except Exception as e:
            logger.error(f"Erro ao salvar cache no PostgreSQL: {e}")
            return self.demo_manager.save_cache(consensus_data, user_id=user_id)

    async def invalidate_cache(self, user_id: Optional[int] = None):
        self.demo_manager.invalidate_cache(user_id=user_id)
        if self.is_connected and self.pool:
            try:
                async with self.pool.acquire() as conn:
                    if user_id is not None:
                        await conn.execute("UPDATE llm_consensus_cache SET is_active = FALSE WHERE is_active = TRUE AND user_id = $1;", user_id)
                    else:
                        await conn.execute("UPDATE llm_consensus_cache SET is_active = FALSE WHERE is_active = TRUE AND user_id IS NULL;")
            except Exception as e:
                logger.error(f"Erro ao invalidar cache no PostgreSQL: {e}")

    async def update_last_login(self, user_id: int):
        """Atualiza last_login_at do usuário após autenticação bem-sucedida."""
        if self.is_connected and self.pool:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET last_login_at = NOW() WHERE id = $1;",
                    user_id
                )

    # -------------------------------------------------------------------------
    # Budget Months
    # -------------------------------------------------------------------------
    async def get_or_create_budget_month(self, user_id: int, year: int, month: int) -> Dict[str, Any]:
        """Retorna ou cria o período mensal. Auto-fecha meses passados."""
        import calendar
        label = f"{calendar.month_name[month]}/{year}"
        if self.is_connected and self.pool:
            async with self.pool.acquire() as conn:
                # Auto-fechar meses anteriores ao atual
                now = datetime.now(timezone.utc)
                await conn.execute("""
                    UPDATE budget_months SET is_closed = TRUE
                    WHERE user_id = $1
                      AND is_closed = FALSE
                      AND (year < $2 OR (year = $2 AND month < $3))
                """, user_id, now.year, now.month)
                # Upsert do mês solicitado
                row = await conn.fetchrow("""
                    INSERT INTO budget_months (user_id, year, month, label)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, year, month) DO UPDATE SET label = EXCLUDED.label
                    RETURNING id, user_id, year, month, label, is_closed, notes, created_at
                """, user_id, year, month, label)
                return dict(row)
        # Demo fallback
        return {"id": 1, "user_id": user_id, "year": year, "month": month,
                "label": label, "is_closed": False, "notes": None}

    async def get_monthly_summary(self, user_id: int, year: int, month: int) -> Dict[str, Any]:
        """Calcula o resumo financeiro do mês a partir dos lançamentos reais."""
        bm = await self.get_or_create_budget_month(user_id, year, month)
        if not self.is_connected or not self.pool:
            return self.demo_manager.get_financial_summary("Atual", user_id=user_id)
        async with self.pool.acquire() as conn:
            income_row = await conn.fetchrow("""
                SELECT COALESCE(SUM(amount),0) AS total FROM income_entries
                WHERE budget_month_id = $1 AND user_id = $2
            """, bm["id"], user_id)
            exp_rows = await conn.fetch("""
                SELECT expense_type, COALESCE(SUM(amount),0) AS total
                FROM expense_entries
                WHERE budget_month_id = $1 AND user_id = $2
                GROUP BY expense_type
            """, bm["id"], user_id)
        totals = {r["expense_type"]: float(r["total"]) for r in exp_rows}
        total_income = float(income_row["total"])
        fixed = totals.get("fixed", 0)
        variable = totals.get("variable", 0)
        debt = totals.get("debt", 0)
        card = totals.get("card", 0)
        total_out = fixed + variable + debt + card
        import calendar
        return {
            "year": year, "month": month,
            "label": bm["label"] or f"{calendar.month_name[month]}/{year}",
            "total_income": round(total_income, 2),
            "total_expenses_fixed": round(fixed, 2),
            "total_expenses_variable": round(variable, 2),
            "total_expenses_debt": round(debt, 2),
            "total_expenses_card": round(card, 2),
            "total_outflow": round(total_out, 2),
            "net_surplus": round(total_income - total_out, 2),
            "is_closed": bm["is_closed"],
        }

    async def close_budget_month(self, user_id: int, year: int, month: int) -> bool:
        """Fecha um período mensal tornando-o somente-leitura."""
        if self.is_connected and self.pool:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE budget_months SET is_closed = TRUE
                    WHERE user_id = $1 AND year = $2 AND month = $3
                """, user_id, year, month)
        return True

    async def _check_month_editable(self, budget_month_id: int, user_id: int):
        """Lança ValueError se o mês estiver fechado. Chame antes de qualquer write."""
        if self.is_connected and self.pool:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT is_closed FROM budget_months WHERE id = $1 AND user_id = $2",
                    budget_month_id, user_id
                )
                if row and row["is_closed"]:
                    raise ValueError("Mês encerrado — não é possível editar lançamentos de períodos fechados.")

    # -------------------------------------------------------------------------
    # Expense Categories
    # -------------------------------------------------------------------------
    async def get_expense_categories(self, user_id: int) -> List[Dict[str, Any]]:
        if not self.is_connected or not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, user_id, name, category, icon, color, is_active, sort_order
                FROM expense_categories
                WHERE user_id = $1 AND is_active = TRUE
                ORDER BY sort_order, name
            """, user_id)
        return [dict(r) for r in rows]

    async def create_expense_category(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_connected or not self.pool:
            return {"id": 0, **data}
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO expense_categories (user_id, name, category, icon, color, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, name) DO UPDATE
                    SET category=$3, icon=$4, color=$5, sort_order=$6, is_active=TRUE
                RETURNING id, user_id, name, category, icon, color, is_active, sort_order
            """, user_id, data["name"], data["category"],
                data.get("icon"), data.get("color"), data.get("sort_order", 0))
        return dict(row)

    async def update_expense_category(self, user_id: int, cat_id: int, data: Dict[str, Any]) -> bool:
        if not self.is_connected or not self.pool:
            return False
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE expense_categories
                SET name=$3, category=$4, icon=$5, color=$6, sort_order=$7
                WHERE id=$1 AND user_id=$2
            """, cat_id, user_id, data["name"], data["category"],
                data.get("icon"), data.get("color"), data.get("sort_order", 0))
        return True

    async def delete_expense_category(self, user_id: int, cat_id: int) -> bool:
        """Soft-delete: marca is_active=FALSE."""
        if not self.is_connected or not self.pool:
            return False
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE expense_categories SET is_active=FALSE WHERE id=$1 AND user_id=$2",
                cat_id, user_id
            )
        return True

    # -------------------------------------------------------------------------
    # Expense Entries
    # -------------------------------------------------------------------------
    async def get_expense_entries(self, user_id: int, budget_month_id: int) -> List[Dict[str, Any]]:
        if not self.is_connected or not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT e.id, e.user_id, e.budget_month_id, e.category_id,
                       e.description, e.amount, e.expense_type, e.due_date,
                       e.is_paid, e.paid_at, e.installment_current, e.installment_total,
                       e.notes, e.created_at, c.name AS category_name, c.icon AS category_icon
                FROM expense_entries e
                LEFT JOIN expense_categories c ON c.id = e.category_id
                WHERE e.budget_month_id = $1 AND e.user_id = $2
                ORDER BY e.expense_type, e.description
            """, budget_month_id, user_id)
        return [dict(r) for r in rows]

    async def upsert_expense_entry(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        bm_id = data["budget_month_id"]
        await self._check_month_editable(bm_id, user_id)
        if not self.is_connected or not self.pool:
            return {"id": 0, **data}
        entry_id = data.get("id")
        async with self.pool.acquire() as conn:
            if entry_id:
                row = await conn.fetchrow("""
                    UPDATE expense_entries SET
                        description=$3, amount=$4, expense_type=$5, category_id=$6,
                        due_date=$7, is_paid=$8, paid_at=$9,
                        installment_current=$10, installment_total=$11, notes=$12
                    WHERE id=$1 AND user_id=$2
                    RETURNING *
                """, entry_id, user_id,
                    data["description"], float(data["amount"]), data.get("expense_type", "fixed"),
                    data.get("category_id"), data.get("due_date"), data.get("is_paid", False),
                    data.get("paid_at"), data.get("installment_current"), data.get("installment_total"),
                    data.get("notes"))
            else:
                row = await conn.fetchrow("""
                    INSERT INTO expense_entries
                        (user_id, budget_month_id, description, amount, expense_type,
                         category_id, due_date, is_paid, installment_current, installment_total, notes)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    RETURNING *
                """, user_id, bm_id,
                    data["description"], float(data["amount"]), data.get("expense_type", "fixed"),
                    data.get("category_id"), data.get("due_date"), data.get("is_paid", False),
                    data.get("installment_current"), data.get("installment_total"), data.get("notes"))
        return dict(row)

    async def delete_expense_entry(self, user_id: int, entry_id: int) -> bool:
        # Precisamos checar o mes antes de deletar
        if self.is_connected and self.pool:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT budget_month_id FROM expense_entries WHERE id=$1 AND user_id=$2",
                    entry_id, user_id
                )
                if row:
                    await self._check_month_editable(row["budget_month_id"], user_id)
                await conn.execute(
                    "DELETE FROM expense_entries WHERE id=$1 AND user_id=$2",
                    entry_id, user_id
                )
        return True

    # -------------------------------------------------------------------------
    # Income Entries
    # -------------------------------------------------------------------------
    async def get_income_entries(self, user_id: int, budget_month_id: int) -> List[Dict[str, Any]]:
        if not self.is_connected or not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, user_id, budget_month_id, description, amount,
                       income_type, is_received, received_at, notes, created_at
                FROM income_entries
                WHERE budget_month_id=$1 AND user_id=$2
                ORDER BY income_type, description
            """, budget_month_id, user_id)
        return [dict(r) for r in rows]

    async def upsert_income_entry(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        bm_id = data["budget_month_id"]
        await self._check_month_editable(bm_id, user_id)
        if not self.is_connected or not self.pool:
            return {"id": 0, **data}
        entry_id = data.get("id")
        async with self.pool.acquire() as conn:
            if entry_id:
                row = await conn.fetchrow("""
                    UPDATE income_entries SET
                        description=$3, amount=$4, income_type=$5, is_received=$6, received_at=$7, notes=$8
                    WHERE id=$1 AND user_id=$2
                    RETURNING *
                """, entry_id, user_id,
                    data["description"], float(data["amount"]), data.get("income_type", "salary"),
                    data.get("is_received", False), data.get("received_at"), data.get("notes"))
            else:
                row = await conn.fetchrow("""
                    INSERT INTO income_entries (user_id, budget_month_id, description, amount, income_type, is_received, received_at, notes)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    RETURNING *
                """, user_id, bm_id,
                    data["description"], float(data["amount"]), data.get("income_type", "salary"),
                    data.get("is_received", False), data.get("received_at"), data.get("notes"))
        return dict(row)

    async def delete_income_entry(self, user_id: int, entry_id: int) -> bool:
        if self.is_connected and self.pool:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT budget_month_id FROM income_entries WHERE id=$1 AND user_id=$2",
                    entry_id, user_id
                )
                if row:
                    await self._check_month_editable(row["budget_month_id"], user_id)
                await conn.execute("DELETE FROM income_entries WHERE id=$1 AND user_id=$2", entry_id, user_id)
        return True

    # -------------------------------------------------------------------------
    # Financial Goals
    # -------------------------------------------------------------------------
    async def get_active_goal(self, user_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected or not self.pool:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, user_id, title, goal_type, target_amount, target_date,
                       current_amount, monthly_contribution, priority, is_active, notes,
                       created_at, updated_at
                FROM financial_goals
                WHERE user_id=$1 AND is_active=TRUE AND priority=1
                LIMIT 1
            """, user_id)
        return dict(row) if row else None

    async def upsert_goal(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_connected or not self.pool:
            return {"id": 0, **data}
        goal_id = data.get("id")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if data.get("priority", 1) == 1:
                    # Rebaixar prioridade do objetivo anterior
                    await conn.execute("""
                        UPDATE financial_goals SET priority=2 WHERE user_id=$1 AND priority=1 AND is_active=TRUE
                    """, user_id)
                if goal_id:
                    row = await conn.fetchrow("""
                        UPDATE financial_goals SET
                            title=$3, goal_type=$4, target_amount=$5, target_date=$6,
                            current_amount=$7, monthly_contribution=$8, priority=$9,
                            is_active=$10, notes=$11, updated_at=NOW()
                        WHERE id=$1 AND user_id=$2
                        RETURNING *
                    """, goal_id, user_id,
                        data["title"], data["goal_type"], data.get("target_amount"),
                        data.get("target_date"), float(data.get("current_amount", 0)),
                        float(data.get("monthly_contribution", 0)), data.get("priority", 1),
                        data.get("is_active", True), data.get("notes"))
                else:
                    row = await conn.fetchrow("""
                        INSERT INTO financial_goals (user_id, title, goal_type, target_amount, target_date,
                            current_amount, monthly_contribution, priority, notes)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                        RETURNING *
                    """, user_id, data["title"], data["goal_type"], data.get("target_amount"),
                        data.get("target_date"), float(data.get("current_amount", 0)),
                        float(data.get("monthly_contribution", 0)), data.get("priority", 1),
                        data.get("notes"))
        return dict(row)

    async def deactivate_goal(self, user_id: int, goal_id: int) -> bool:
        if self.is_connected and self.pool:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE financial_goals SET is_active=FALSE, updated_at=NOW() WHERE id=$1 AND user_id=$2",
                    goal_id, user_id
                )
        return True

    # -------------------------------------------------------------------------
    # Investment Portfolios (histórico acumulado)
    # -------------------------------------------------------------------------
    async def get_active_portfolio(self, user_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected or not self.pool:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, user_id, consensus_record_id, generated_at, is_active,
                       pct_renda_fixa, pct_tesouro, pct_fiis, pct_acoes,
                       pct_reserva_liquida, pct_cripto, monthly_investment_target,
                       emergency_reserve_target, months_to_goal, projection_json, rationale
                FROM investment_portfolios
                WHERE user_id=$1 AND is_active=TRUE
                ORDER BY generated_at DESC LIMIT 1
            """, user_id)
        return dict(row) if row else None

    async def get_portfolio_history(self, user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Retorna os últimos N portfólios para usar como contexto no próximo prompt."""
        if not self.is_connected or not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, generated_at, is_active, pct_renda_fixa, pct_tesouro, pct_fiis,
                       pct_acoes, pct_reserva_liquida, pct_cripto, monthly_investment_target,
                       months_to_goal, rationale
                FROM investment_portfolios
                WHERE user_id=$1
                ORDER BY generated_at DESC LIMIT $2
            """, user_id, limit)
        return [dict(r) for r in rows]

    async def save_portfolio(self, user_id: int, data: Dict[str, Any], consensus_record_id: Optional[int] = None) -> Dict[str, Any]:
        """Salva novo portfólio. O anterior permanece no histórico (is_active=FALSE)."""
        if not self.is_connected or not self.pool:
            return {"id": 0, **data}
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE investment_portfolios SET is_active=FALSE WHERE user_id=$1 AND is_active=TRUE",
                    user_id
                )
                row = await conn.fetchrow("""
                    INSERT INTO investment_portfolios (
                        user_id, consensus_record_id, pct_renda_fixa, pct_tesouro,
                        pct_fiis, pct_acoes, pct_reserva_liquida, pct_cripto,
                        monthly_investment_target, emergency_reserve_target,
                        months_to_goal, projection_json, rationale
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                    RETURNING *
                """, user_id, consensus_record_id,
                    float(data.get("pct_renda_fixa", 0)), float(data.get("pct_tesouro", 0)),
                    float(data.get("pct_fiis", 0)), float(data.get("pct_acoes", 0)),
                    float(data.get("pct_reserva_liquida", 0)), float(data.get("pct_cripto", 0)),
                    float(data.get("monthly_investment_target", 0)),
                    float(data.get("emergency_reserve_target", 0)),
                    data.get("months_to_goal"),
                    json.dumps(data.get("projection_json")) if data.get("projection_json") else None,
                    data.get("rationale")
                )
        return dict(row)

    # -------------------------------------------------------------------------
    # LLM Individual Responses
    # -------------------------------------------------------------------------
    async def save_llm_individual_response(self, data: Dict[str, Any]) -> bool:
        if not self.is_connected or not self.pool:
            return False
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO llm_individual_responses
                    (consensus_id, user_id, provider_name, round_number,
                     raw_response, allocation, confidence, risk_flags, reasoning)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            """, data["consensus_id"], data["user_id"], data["provider_name"],
                data.get("round_number", 1),
                json.dumps(data.get("raw_response", {})),
                json.dumps(data.get("allocation")) if data.get("allocation") else None,
                data.get("confidence"),
                data.get("risk_flags") or [],
                data.get("reasoning")
            )
        return True

    # -------------------------------------------------------------------------
    # Timeline e Forecast (dados reais)
    # -------------------------------------------------------------------------
    async def get_monthly_timeline(self, user_id: int, months_back: int = 3, months_forward: int = 9) -> List[Dict[str, Any]]:
        """Retroativo + projeção futura personalizada."""
        now = datetime.now(timezone.utc)
        results = []
        for delta in range(-months_back, months_forward + 1):
            # calcular year/month com delta
            total_month = now.month + delta
            year = now.year + (total_month - 1) // 12
            month = ((total_month - 1) % 12) + 1
            try:
                snap = await self.get_monthly_summary(user_id, year, month)
                results.append(snap)
            except Exception as e:
                logger.warning(f"Erro ao carregar mês {year}/{month}: {e}")
        return results

    async def update_financial_inputs(self, new_data: Dict[str, Any], user_id: Optional[int] = None):
        self.demo_manager.update_financial_inputs(new_data, user_id=user_id)
        await self.invalidate_cache(user_id=user_id)


# Instância global compartilhada
db_manager = DatabaseManager()

