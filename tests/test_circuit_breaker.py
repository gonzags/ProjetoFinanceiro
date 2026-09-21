"""
test_circuit_breaker.py - Testes unitários do Circuit Breaker e Resiliência
100% MOCKADOS (zero chamadas a APIs externas).
Valida:
- Entrada em cooldown de 60 segundos ao receber HTTP 429
- Entrada em cooldown ao sofrer Timeout (>12s)
- Pulo automático do provedor em cooldown sem bloquear os demais
- Ativação do fallback local quando todos os provedores estão em cooldown
"""

import time
import pytest
from unittest.mock import patch, MagicMock
import httpx

from llm_router import (
    BaseOpenAICompatibleProvider,
    CircuitBreaker,
    ConsensusEngine,
)


def test_circuit_breaker_cooldown_on_429():
    """Ao receber HTTP 429, provedor deve entrar em cooldown de 60s e ser pulado."""
    cb = CircuitBreaker(cooldown_seconds=60.0)
    pid = "test_provider"

    assert cb.is_available(pid) is True

    # Simular falha por 429
    cb.record_failure(pid, reason="HTTP 429")

    assert cb.is_available(pid) is False
    assert cb.failure_counts[pid] == 1

    # Verificar que o cooldown está configurado para ~60 segundos no futuro
    assert cb.cooldown_until[pid] > time.time() + 50


def test_circuit_breaker_expiration():
    """Após expirar o tempo de cooldown, o provedor deve voltar a ficar disponível."""
    cb = CircuitBreaker(cooldown_seconds=0.1)  # Cooldown ultra-curto para o teste
    pid = "test_expiring_provider"

    cb.record_failure(pid, reason="HTTP 429")
    assert cb.is_available(pid) is False

    # Aguardar expiração
    time.sleep(0.15)
    assert cb.is_available(pid) is True


@pytest.mark.asyncio
async def test_provider_skips_call_when_in_cooldown():
    """Um provedor em cooldown deve retornar None imediatamente sem realizar requisição HTTP."""
    cb = CircuitBreaker(cooldown_seconds=60.0)
    provider = BaseOpenAICompatibleProvider(
        provider_id="groq",
        name="Groq",
        role="Proposer",
        base_url="https://mock.groq.com",
        api_key="valid_key",
        model="mock",
        circuit_breaker=cb
    )

    # Forçar cooldown no provedor
    cb.record_failure("groq", reason="429 prévio")
    assert cb.is_available("groq") is False

    with patch("httpx.AsyncClient.post") as mock_post:
        resp = await provider.generate("prompt", {})
        assert resp is None
        # Nenhuma requisição HTTP foi feita!
        mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_provider_triggers_cooldown_on_timeout():
    """Estouro de timeout no httpx deve acionar o circuit breaker."""
    cb = CircuitBreaker(cooldown_seconds=60.0)
    provider = BaseOpenAICompatibleProvider(
        provider_id="gemini",
        name="Gemini",
        role="Auditor",
        base_url="https://mock.gemini.com",
        api_key="valid_key",
        model="mock",
        circuit_breaker=cb
    )

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout após 12s")):
        resp = await provider.generate("prompt", {})
        assert resp is None
        assert cb.is_available("gemini") is False
        assert cb.failure_counts["gemini"] == 1


@pytest.mark.asyncio
async def test_all_providers_down_activates_local_fallback():
    """Se todos os provedores estiverem em cooldown, o motor ativa imediatamente o fallback local."""
    engine = ConsensusEngine()
    
    # Colocar todos os 5 provedores em cooldown
    for pid in ["groq", "gemini", "mistral", "openrouter", "cloudflare"]:
        engine.circuit_breaker.record_failure(pid, reason="Teste todos em cooldown")

    summary = {
        "total_income": 2133.42,
        "fixed_costs": 285.00,
        "debts_total": 1236.83,
        "special_events": 500.00
    }

    result = await engine.run_consensus_loop(summary, force_recalculate=True)

    assert result.consensus_status == "deterministico_local"
    assert result.participating_providers == []
    assert result.allocation["necessidades"] > 0
    assert result.confidence_score >= 0.70
