"""
utils.py - Módulo de Banco de Dados, Cálculos Financeiros e Cache (Ledger Horizon)
Suporte para PostgreSQL 16 (asyncpg) com fallback automático para DemoDataManager em memória.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
from pydantic import BaseModel, Field

logger = logging.getLogger("ledger_horizon.utils")

# -----------------------------------------------------------------------------
# Modelos de Dados Pydantic
# -----------------------------------------------------------------------------

class AllocationSchema(BaseModel):
    necessidades: float = Field(..., description="Percentual para necessidades (0.0 a 1.0 ou 0 a 100)")
    desejos: float = Field(..., description="Percentual para desejos (0.0 a 1.0 ou 0 a 100)")
    futuro: float = Field(..., description="Percentual para futuro/dívidas/investimentos")


class ConsensusRecord(BaseModel):
    id: Optional[int] = None
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
# Gerenciador em Memória para Desenvolvimento / Demonstração
# -----------------------------------------------------------------------------

class DemoDataManager:
    """Armazena e manipula os dados em memória quando o PostgreSQL não estiver disponível."""
    
    def __init__(self):
        self.seed = load_seed_data()
        self.cached_consensus: Optional[ConsensusRecord] = None
        self._init_default_cache()

    def _init_default_cache(self):
        summary = self.get_financial_summary("Outubro")
        res = compute_deterministic_local_allocation(summary)
        self.cached_consensus = ConsensusRecord(
            id=1,
            created_at=datetime.now(timezone.utc),
            allocation=res["allocation"],
            confidence_score=res["confidence_score"],
            risk_flags=res["risk_flags"],
            reasoning_summary=res["reasoning_summary"],
            consensus_status=res["consensus_status"],
            provider_metadata=res["provider_metadata"],
            is_active=True
        )

    def get_financial_summary(self, month: str = "Outubro") -> Dict[str, Any]:
        profile = self.seed["profile"]
        salary_net = profile["salary_net"]
        
        # Somar recebíveis do mês
        receivables_month = sum(
            r["amount"] for r in profile.get("receivables", [])
            if month in r.get("months", [])
        )
        total_income = salary_net + receivables_month

        # Somar custos fixos
        fixed_costs = sum(item["amount"] for item in self.seed.get("fixed_expenses", []))

        # Somar faturas
        cards = self.seed.get("card_schedules", {})
        picpay_amount = cards.get("PicPay", {}).get("installments", {}).get(month, 0.0)
        nubank_amount = cards.get("Nubank", {}).get("installments", {}).get(month, 0.0)

        # Compromissos pontuais
        special = sum(
            item["amount"] for item in self.seed.get("one_off_commitments", [])
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

    def get_timeline(self) -> List[MonthlyCashFlow]:
        months = ["Outubro", "Novembro", "Dezembro", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto"]
        timeline = []
        for m in months:
            summary = self.get_financial_summary(m)
            
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

    def get_active_cache(self, max_age_hours: int = 24) -> Optional[ConsensusRecord]:
        if not self.cached_consensus or not self.cached_consensus.is_active:
            return None
        
        now = datetime.now(timezone.utc)
        age = (now - self.cached_consensus.created_at).total_seconds() / 3600.0
        if age > max_age_hours:
            logger.info("Cache expirado por idade (>24h).")
            return None
        return self.cached_consensus

    def save_cache(self, consensus_data: Dict[str, Any]) -> ConsensusRecord:
        rec = ConsensusRecord(
            id=1,
            created_at=datetime.now(timezone.utc),
            allocation=consensus_data["allocation"],
            confidence_score=consensus_data["confidence_score"],
            risk_flags=consensus_data["risk_flags"],
            reasoning_summary=consensus_data["reasoning_summary"],
            consensus_status=consensus_data.get("consensus_status", "total"),
            provider_metadata=consensus_data.get("provider_metadata", {}),
            is_active=True
        )
        self.cached_consensus = rec
        return rec

    def invalidate_cache(self):
        if self.cached_consensus:
            self.cached_consensus.is_active = False
            logger.info("Cache de consenso invalidado com sucesso.")

    def update_financial_inputs(self, new_data: Dict[str, Any]):
        """Atualiza valores via questionário e invalida o cache."""
        if "salary_net" in new_data:
            self.seed["profile"]["salary_net"] = float(new_data["salary_net"])
        if "fixed_expenses" in new_data:
            self.seed["fixed_expenses"] = new_data["fixed_expenses"]
        if "card_schedules" in new_data:
            self.seed["card_schedules"] = new_data["card_schedules"]
        if "one_off_commitments" in new_data:
            self.seed["one_off_commitments"] = new_data["one_off_commitments"]
            
        self.invalidate_cache()


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
        database = os.getenv("POSTGRES_DB", "ledger_horizon")
        user = os.getenv("POSTGRES_USER", "postgres")
        password = os.getenv("POSTGRES_PASSWORD", "postgres")

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
        
        create_cache_table = """
        CREATE TABLE IF NOT EXISTS llm_consensus_cache (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            allocation JSONB NOT NULL,
            confidence_score NUMERIC(5, 2) NOT NULL,
            risk_flags JSONB NOT NULL,
            reasoning_summary TEXT NOT NULL,
            consensus_status VARCHAR(50) NOT NULL,
            provider_metadata JSONB DEFAULT '{}'::jsonb,
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        );
        """
        async with self.pool.acquire() as conn:
            await conn.execute(create_cache_table)
            logger.info("Tabela llm_consensus_cache verificada/criada.")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self.is_connected = False
            logger.info("Pool PostgreSQL encerrado.")

    def get_connection_status(self) -> str:
        """
        Retorna um dos 3 estados do badge:
        1. "Data Warehouse: PostgreSQL 16 (Connected)"
        2. "Modo demonstração — dados em cache local"
        """
        if self.is_connected:
            return "Data Warehouse: PostgreSQL 16 (Connected)"
        return "Modo demonstração — dados em cache local"

    async def get_financial_summary(self, month: str = "Outubro") -> Dict[str, Any]:
        return self.demo_manager.get_financial_summary(month)

    async def get_timeline(self) -> List[MonthlyCashFlow]:
        return self.demo_manager.get_timeline()

    async def get_active_cache(self, max_age_hours: int = 24) -> Optional[ConsensusRecord]:
        if not self.is_connected or not self.pool:
            return self.demo_manager.get_active_cache(max_age_hours)

        query = """
        SELECT id, created_at, allocation, confidence_score, risk_flags, reasoning_summary, 
               consensus_status, provider_metadata, is_active
        FROM llm_consensus_cache
        WHERE is_active = TRUE 
          AND created_at >= NOW() - INTERVAL '1 hour' * $1
        ORDER BY created_at DESC
        LIMIT 1;
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, max_age_hours)
                if row:
                    return ConsensusRecord(
                        id=row["id"],
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

        return self.demo_manager.get_active_cache(max_age_hours)

    async def save_cache(self, consensus_data: Dict[str, Any]) -> ConsensusRecord:
        if not self.is_connected or not self.pool:
            return self.demo_manager.save_cache(consensus_data)

        # Invalida os caches anteriores
        invalidate_query = "UPDATE llm_consensus_cache SET is_active = FALSE WHERE is_active = TRUE;"
        insert_query = """
        INSERT INTO llm_consensus_cache (
            created_at, allocation, confidence_score, risk_flags, reasoning_summary, 
            consensus_status, provider_metadata, is_active
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE)
        RETURNING id, created_at;
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(invalidate_query)
                    now = datetime.now(timezone.utc)
                    row = await conn.fetchrow(
                        insert_query,
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
            return self.demo_manager.save_cache(consensus_data)

    async def invalidate_cache(self):
        self.demo_manager.invalidate_cache()
        if self.is_connected and self.pool:
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute("UPDATE llm_consensus_cache SET is_active = FALSE WHERE is_active = TRUE;")
            except Exception as e:
                logger.error(f"Erro ao invalidar cache no PostgreSQL: {e}")

    async def update_financial_inputs(self, new_data: Dict[str, Any]):
        self.demo_manager.update_financial_inputs(new_data)
        await self.invalidate_cache()


# Instância global compartilhada
db_manager = DatabaseManager()
