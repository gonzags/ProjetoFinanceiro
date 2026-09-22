"""
llm_router.py - Motor de Consenso Multi-IA (Ledger Horizon)
Implementa a arquitetura de 5 provedores gratuitos, validação de schema JSON obrigatório,
convergência computável, teto de 3 rodadas, circuit breaker (cooldown de 60s) e fallback local.
Conforme especificado em claudeaudita.pdf (v4 Revisado).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

import httpx
import yaml
from pydantic import BaseModel, Field, ValidationError

from utils import (
    AllocationSchema,
    ConsensusRecord,
    compute_deterministic_local_allocation,
    db_manager,
)

logger = logging.getLogger("ledger_horizon.llm_router")

BASE_DIR = Path(__file__).resolve().parent

# -----------------------------------------------------------------------------
# Schemas Estruturados Obrigatórios (Pydantic)
# -----------------------------------------------------------------------------

class AgentAllocation(BaseModel):
    necessidades: float = Field(..., ge=0.0, le=100.0, description="Percentual para despesas essenciais")
    desejos: float = Field(..., ge=0.0, le=100.0, description="Percentual para lazer e desejos")
    futuro: float = Field(..., ge=0.0, le=100.0, description="Percentual para quitação de dívidas e reservas")


class LLMResponse(BaseModel):
    provider_id: str
    provider_name: str
    allocation: AgentAllocation
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    risk_flags: List[str] = Field(default_factory=list)
    reasoning_summary: str = Field(..., max_length=350)
    latency_ms: float = 0.0


class ConsensusExecutionResult(BaseModel):
    allocation: Dict[str, float]
    confidence_score: float
    risk_flags: List[str]
    reasoning_summary: str
    consensus_status: str  # "total", "parcial", "deterministico_local"
    rounds_executed: int
    participating_providers: List[str]
    provider_metadata: Dict[str, Any]


# -----------------------------------------------------------------------------
# Circuit Breaker com Cooldown de 60s em Memória
# -----------------------------------------------------------------------------

class CircuitBreaker:
    """Gerencia falhas de 429 e timeout por provedor, isolando-os por 60 segundos."""
    
    def __init__(self, cooldown_seconds: float = 60.0):
        self.cooldown_seconds = cooldown_seconds
        # provider_id -> timestamp até o qual o provedor está em cooldown
        self.cooldown_until: Dict[str, float] = {}
        # provider_id -> contagem de falhas consecutivas
        self.failure_counts: Dict[str, int] = {}

    def is_available(self, provider_id: str) -> bool:
        now = time.time()
        until = self.cooldown_until.get(provider_id, 0.0)
        if now < until:
            remaining = int(until - now)
            logger.info(f"Provedor [{provider_id}] em cooldown por mais {remaining}s. Ignorando chamada.")
            return False
        return True

    def record_success(self, provider_id: str):
        self.failure_counts[provider_id] = 0
        if provider_id in self.cooldown_until:
            del self.cooldown_until[provider_id]

    def record_failure(self, provider_id: str, reason: str = "error"):
        now = time.time()
        self.failure_counts[provider_id] = self.failure_counts.get(provider_id, 0) + 1
        self.cooldown_until[provider_id] = now + self.cooldown_seconds
        logger.warning(
            f"Provedor [{provider_id}] falhou ({reason}). "
            f"Entrou em cooldown por {self.cooldown_seconds}s. Total falhas: {self.failure_counts[provider_id]}"
        )


# -----------------------------------------------------------------------------
# Interface e Implementações de Provedores
# -----------------------------------------------------------------------------

@runtime_checkable
class LLMProviderProtocol(Protocol):
    provider_id: str
    name: str
    role: str

    async def generate(self, prompt: str, context: Dict[str, Any], timeout: float = 12.0) -> Optional[LLMResponse]:
        ...


class BaseOpenAICompatibleProvider:
    """Implementa a comunicação com endpoints compatíveis com OpenAI."""
    
    def __init__(
        self,
        provider_id: str,
        name: str,
        role: str,
        base_url: str,
        api_key: Optional[str],
        model: str,
        circuit_breaker: CircuitBreaker,
        timeout: float = 12.0,
        max_tokens: int = 500,
        temperature: float = 0.2
    ):
        self.provider_id = provider_id
        self.name = name
        self.role = role
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.circuit_breaker = circuit_breaker
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip() and not self.api_key.startswith("your_"))

    async def generate(self, prompt: str, context: Dict[str, Any], timeout: Optional[float] = None) -> Optional[LLMResponse]:
        if not self.is_configured():
            logger.debug(f"[{self.name}] não configurado (chave ausente no .env).")
            return None

        if not self.circuit_breaker.is_available(self.provider_id):
            return None

        effective_timeout = timeout or self.timeout
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Prompt do sistema exigindo estritamente JSON
        system_instruction = (
            "Você é um agente analista financeiro integrante de um comitê de deliberação orçamentária. "
            "Responda ESTRITAMENTE em formato JSON com o seguinte schema exato:\n"
            "{\n"
            '  "allocation": {"necessidades": float, "desejos": float, "futuro": float},\n'
            '  "confidence_score": float,\n'
            '  "risk_flags": ["string"],\n'
            '  "reasoning_summary": "string (máximo 300 caracteres)"\n'
            "}\n"
            "A soma de necessidades + desejos + futuro DEVE totalizar 100.0. "
            "Não inclua markdown (` ```json `), apenas o JSON puro."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"}
        }

        url = f"{self.base_url}/chat/completions"

        # Retry de 1 tentativa se falhar schema
        for attempt in range(2):
            start_time = time.time()
            try:
                async with httpx.AsyncClient(timeout=effective_timeout) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    latency = (time.time() - start_time) * 1000.0

                    if resp.status_code == 429:
                        self.circuit_breaker.record_failure(self.provider_id, reason="HTTP 429 Too Many Requests")
                        return None
                    elif resp.status_code >= 500:
                        self.circuit_breaker.record_failure(self.provider_id, reason=f"HTTP {resp.status_code}")
                        return None
                    elif resp.status_code != 200:
                        logger.warning(f"[{self.name}] erro HTTP {resp.status_code}: {resp.text[:100]}")
                        return None

                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    # Parsing e Validação Pydantic
                    parsed = json.loads(content)
                    alloc_raw = parsed["allocation"]
                    
                    # Normalização de percentual se veio em decimal (ex: 0.5 em vez de 50)
                    if (alloc_raw.get("necessidades", 0) <= 1.0 and 
                        alloc_raw.get("desejos", 0) <= 1.0 and 
                        alloc_raw.get("futuro", 0) <= 1.0):
                        alloc_raw = {k: v * 100.0 for k, v in alloc_raw.items()}

                    validated_alloc = AgentAllocation(**alloc_raw)
                    validated_resp = LLMResponse(
                        provider_id=self.provider_id,
                        provider_name=self.name,
                        allocation=validated_alloc,
                        confidence_score=float(parsed.get("confidence_score", 0.75)),
                        risk_flags=list(parsed.get("risk_flags", [])),
                        reasoning_summary=str(parsed.get("reasoning_summary", ""))[:300],
                        latency_ms=round(latency, 1)
                    )

                    self.circuit_breaker.record_success(self.provider_id)
                    # Não logar dados financeiros brutos por segurança!
                    logger.info(f"[{self.name}] Resposta validada com sucesso em {latency:.1f}ms.")
                    return validated_resp

            except (httpx.TimeoutException, asyncio.TimeoutError):
                self.circuit_breaker.record_failure(self.provider_id, reason="Timeout (>12s)")
                return None
            except (json.JSONDecodeError, ValidationError, KeyError) as e:
                logger.warning(f"[{self.name}] Falha na validação do schema JSON (tentativa {attempt + 1}/2): {e}")
                if attempt == 0:
                    # Retry único com reforço de schema
                    payload["messages"].append({
                        "role": "user",
                        "content": "ATENÇÃO: Sua resposta anterior não atendeu ao schema JSON exigido. Retorne SOMENTE o JSON válido sem nenhum texto adicional."
                    })
                    continue
                else:
                    logger.warning(f"[{self.name}] Descartado da rodada após 2 falhas consecutivas de schema.")
                    return None
            except Exception as e:
                logger.error(f"[{self.name}] Exceção inesperada: {type(e).__name__} - {e}")
                self.circuit_breaker.record_failure(self.provider_id, reason=str(e))
                return None

        return None


# -----------------------------------------------------------------------------
# Orquestrador do Motor de Consenso
# -----------------------------------------------------------------------------

class ConsensusEngine:
    """Orquestrador das 3 rodadas de deliberação conforme fluxograma de claudeaudita.pdf."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or (BASE_DIR / "providers.yaml")
        self.config = self._load_config()
        settings = self.config.get("settings", {})
        
        self.cooldown_sec = float(settings.get("circuit_breaker_cooldown_seconds", 60.0))
        self.timeout_sec = float(settings.get("request_timeout_seconds", 12.0))
        self.divergence_threshold = float(settings.get("convergence_divergence_threshold", 0.05)) * 100.0  # 5.0 pontos
        self.min_confidence = float(settings.get("convergence_min_confidence", 0.70))
        self.max_rounds = int(settings.get("max_consensus_rounds", 3))

        self.circuit_breaker = CircuitBreaker(cooldown_seconds=self.cooldown_sec)
        self.providers: Dict[str, BaseOpenAICompatibleProvider] = {}
        self._init_providers()

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
            except Exception as e:
                logger.error(f"Erro ao ler {self.config_path}: {e}")
        return {}

    def _init_providers(self):
        providers_cfg = self.config.get("providers", {})
        
        for pid, cfg in providers_cfg.items():
            env_key = cfg.get("env_key")
            api_key = os.getenv(env_key) if env_key else None
            
            env_model = cfg.get("env_model")
            model = (os.getenv(env_model) if env_model else None) or cfg.get("default_model", "")
            
            base_url = cfg.get("base_url", "")
            if pid == "cloudflare":
                acc_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "dummy_account")
                base_url = cfg.get("base_url_template", "").replace("{account_id}", acc_id)

            self.providers[pid] = BaseOpenAICompatibleProvider(
                provider_id=pid,
                name=cfg.get("name", pid),
                role=cfg.get("role", ""),
                base_url=base_url,
                api_key=api_key,
                model=model,
                circuit_breaker=self.circuit_breaker,
                timeout=self.timeout_sec,
                max_tokens=cfg.get("max_tokens", 500),
                temperature=cfg.get("temperature", 0.2)
            )

    def check_convergence(self, responses: List[LLMResponse]) -> Tuple[bool, float]:
        """
        Critério de convergência computável (claudeaudita.pdf seção 2.3):
        - Divergência = maior diferença absoluta entre as alocações de 2 agentes na mesma rodada.
        - Convergência atingida se: divergência <= 5 pontos percentuais E todos os confidence_score >= 0.7.
        """
        if len(responses) < 2:
            # Com apenas 1 agente, consideramos convergência se a confiança for alta
            if len(responses) == 1 and responses[0].confidence_score >= self.min_confidence:
                return True, 0.0
            return False, 999.0

        max_div = 0.0
        for i in range(len(responses)):
            for j in range(i + 1, len(responses)):
                a1 = responses[i].allocation
                a2 = responses[j].allocation
                diff_nec = abs(a1.necessidades - a2.necessidades)
                diff_des = abs(a1.desejos - a2.desejos)
                diff_fut = abs(a1.futuro - a2.futuro)
                max_diff_pair = max(diff_nec, diff_des, diff_fut)
                if max_diff_pair > max_div:
                    max_div = max_diff_pair

        all_confident = all(r.confidence_score >= self.min_confidence for r in responses)
        converged = (max_div <= self.divergence_threshold) and all_confident
        return converged, max_div

    def _build_prompt(self, financial_summary: Dict[str, Any]) -> str:
        """Cria o prompt estruturado de deliberação orçamentária."""
        income = financial_summary.get("total_income", 2133.42)
        fixed = financial_summary.get("fixed_costs", 285.00)
        debts = financial_summary.get("debts_total", 1236.83)
        special = financial_summary.get("special_events", 500.00)
        surplus = financial_summary.get("net_surplus", 111.59)
        month = financial_summary.get("month", "Outubro")

        return (
            f"Analise o fluxo financeiro para o mês de {month}:\n"
            f"- Renda Líquida Total: R$ {income:.2f}\n"
            f"- Custos Fixos Essenciais: R$ {fixed:.2f}\n"
            f"- Dívidas em Cartão/Parcelamentos: R$ {debts:.2f}\n"
            f"- Eventos Especiais/Compromissos Extras: R$ {special:.2f}\n"
            f"- Sobra Líquida Prevista: R$ {surplus:.2f}\n\n"
            f"Determine a alocação percentual recomendada entre: 'necessidades', 'desejos' e 'futuro' (soma = 100.0). "
            f"Indique o índice de confiança (0.0 a 1.0), liste flags de risco específicas e sintetize o parecer em até 300 caracteres."
        )

    async def run_consensus_loop(
        self,
        financial_summary: Dict[str, Any],
        force_recalculate: bool = False,
        user_id: Optional[int] = None
    ) -> ConsensusExecutionResult:
        """
        Executa o fluxo completo:
        1. Verifica cache ativo no Postgres (<24h).
        2. Se inválido ou forçado, executa no máximo 3 rodadas conforme o fluxograma.
        3. Se todos indisponíveis, cai no fallback determinístico local.
        4. Salva no cache.
        """
        # 1. Verificar cache existente
        if not force_recalculate:
            cached = await db_manager.get_active_cache(max_age_hours=24, user_id=user_id)
            if cached:
                logger.info("Retornando consenso do cache ativo.")
                return ConsensusExecutionResult(
                    allocation=cached.allocation,
                    confidence_score=cached.confidence_score,
                    risk_flags=cached.risk_flags,
                    reasoning_summary=cached.reasoning_summary,
                    consensus_status=cached.consensus_status,
                    rounds_executed=0,
                    participating_providers=list(cached.provider_metadata.get("providers", [])),
                    provider_metadata=cached.provider_metadata
                )

        prompt = self._build_prompt(financial_summary)

        # Configuração das rodadas conforme claudeaudita.pdf página 6:
        # Rodada 1: Groq + Gemini
        # Rodada 2: Mistral + OpenRouter
        # Rodada 3: Cloudflare Workers AI
        round_groups = [
            ["groq", "gemini"],
            ["mistral", "openrouter"],
            ["cloudflare"]
        ]

        all_collected_responses: List[LLMResponse] = []
        status = "parcial"
        rounds_run = 0

        for r_idx, group in enumerate(round_groups):
            rounds_run = r_idx + 1
            tasks = []
            for pid in group:
                provider = self.providers.get(pid)
                if provider and provider.is_configured() and self.circuit_breaker.is_available(pid):
                    tasks.append(provider.generate(prompt, financial_summary, timeout=self.timeout_sec))

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                valid_this_round = [r for r in results if isinstance(r, LLMResponse)]
                all_collected_responses.extend(valid_this_round)

                # Verifica convergência com as respostas obtidas até esta rodada
                if len(all_collected_responses) >= 2:
                    converged, div = self.check_convergence(all_collected_responses)
                    if converged:
                        status = "total"
                        logger.info(f"Convergência atingida na Rodada {rounds_run} (divergência={div:.1f}%).")
                        break
            else:
                logger.debug(f"Rodada {rounds_run}: Nenhum provedor disponível no grupo {group}.")

        # Se nenhum provedor respondeu (ou nenhum configurado), ativar Fallback Determinístico Local
        if not all_collected_responses:
            logger.warning("Todos os 5 provedores indisponíveis/não configurados. Ativando fallback determinístico local.")
            local_res = compute_deterministic_local_allocation(financial_summary)
            await db_manager.save_cache(local_res, user_id=user_id)
            return ConsensusExecutionResult(
                allocation=local_res["allocation"],
                confidence_score=local_res["confidence_score"],
                risk_flags=local_res["risk_flags"],
                reasoning_summary=local_res["reasoning_summary"],
                consensus_status="deterministico_local",
                rounds_executed=rounds_run,
                participating_providers=[],
                provider_metadata=local_res["provider_metadata"]
            )

        # Se temos respostas, harmonizar resultado
        # Ordenar pelo maior confidence_score
        all_collected_responses.sort(key=lambda x: x.confidence_score, reverse=True)
        top_agent = all_collected_responses[0]

        # Média ponderada das alocações dos agentes participantes
        total_conf = sum(r.confidence_score for r in all_collected_responses)
        avg_nec = sum(r.allocation.necessidades * r.confidence_score for r in all_collected_responses) / total_conf
        avg_des = sum(r.allocation.desejos * r.confidence_score for r in all_collected_responses) / total_conf
        avg_fut = sum(r.allocation.futuro * r.confidence_score for r in all_collected_responses) / total_conf

        # Normalizar para somar 100%
        soma = avg_nec + avg_des + avg_fut
        fator = 100.0 / soma if soma > 0 else 1.0
        final_alloc = {
            "necessidades": round(avg_nec * fator, 1),
            "desejos": round(avg_des * fator, 1),
            "futuro": round(avg_fut * fator, 1)
        }

        # Consolidar risk_flags únicas
        all_flags = []
        for r in all_collected_responses:
            for flag in r.risk_flags:
                if flag not in all_flags:
                    all_flags.append(flag)

        provider_names = [r.provider_name for r in all_collected_responses]
        meta = {
            "providers": provider_names,
            "latencies": {r.provider_name: r.latency_ms for r in all_collected_responses},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        data_to_cache = {
            "allocation": final_alloc,
            "confidence_score": round(top_agent.confidence_score, 2),
            "risk_flags": all_flags[:4],  # até 4 flags principais
            "reasoning_summary": top_agent.reasoning_summary,
            "consensus_status": status,
            "provider_metadata": meta
        }

        await db_manager.save_cache(data_to_cache, user_id=user_id)

        return ConsensusExecutionResult(
            allocation=final_alloc,
            confidence_score=round(top_agent.confidence_score, 2),
            risk_flags=all_flags[:4],
            reasoning_summary=top_agent.reasoning_summary,
            consensus_status=status,
            rounds_executed=rounds_run,
            participating_providers=provider_names,
            provider_metadata=meta
        )


# Instância global do motor de consenso
consensus_engine = ConsensusEngine()
