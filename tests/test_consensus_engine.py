"""
test_consensus_engine.py - Testes unitários do Motor de Consenso Multi-IA
100% MOCKADOS (zero chamadas a APIs externas, zero consumo de cota gratuita).
Valida:
- Critério computável de convergência (divergência <= 5% e confiança >= 0.7)
- Validação de schema Pydantic e 1 retry em resposta corrompida
- Teto de 3 rodadas e status 'parcial' vs 'total'
- Fallback determinístico local em modo de emergência
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from llm_router import (
    AgentAllocation,
    BaseOpenAICompatibleProvider,
    CircuitBreaker,
    ConsensusEngine,
    LLMResponse,
)
from utils import compute_deterministic_local_allocation


def test_computable_convergence_success():
    """Dois agentes com alocações próximas (diff <= 5%) e confiança >= 0.7 devem convergir."""
    engine = ConsensusEngine()

    resp1 = LLMResponse(
        provider_id="groq",
        provider_name="Groq",
        allocation=AgentAllocation(necessidades=50.0, desejos=30.0, futuro=20.0),
        confidence_score=0.85,
        risk_flags=[],
        reasoning_summary="Recomendação equilibrada."
    )
    resp2 = LLMResponse(
        provider_id="gemini",
        provider_name="Gemini",
        allocation=AgentAllocation(necessidades=52.0, desejos=29.0, futuro=19.0),
        confidence_score=0.80,
        risk_flags=[],
        reasoning_summary="Divergência pequena."
    )

    converged, max_div = engine.check_convergence([resp1, resp2])
    assert converged is True
    assert max_div == 2.0  # Max diff: |50 - 52| = 2%


def test_computable_convergence_failure_due_to_divergence():
    """Divergência maior que 5 pontos percentuais não deve convergir."""
    engine = ConsensusEngine()

    resp1 = LLMResponse(
        provider_id="groq",
        provider_name="Groq",
        allocation=AgentAllocation(necessidades=50.0, desejos=30.0, futuro=20.0),
        confidence_score=0.90,
        risk_flags=[],
        reasoning_summary="Aporte agressivo."
    )
    resp2 = LLMResponse(
        provider_id="gemini",
        provider_name="Gemini",
        allocation=AgentAllocation(necessidades=60.0, desejos=25.0, futuro=15.0),
        confidence_score=0.85,
        risk_flags=[],
        reasoning_summary="Foco em segurança."
    )

    converged, max_div = engine.check_convergence([resp1, resp2])
    assert converged is False
    assert max_div == 10.0  # |50 - 60| = 10%


def test_computable_convergence_failure_due_to_low_confidence():
    """Mesmo com alocações idênticas, se a confiança for < 0.70, não converge."""
    engine = ConsensusEngine()

    resp1 = LLMResponse(
        provider_id="groq",
        provider_name="Groq",
        allocation=AgentAllocation(necessidades=50.0, desejos=30.0, futuro=20.0),
        confidence_score=0.65,  # Abaixo de 0.70
        risk_flags=[],
        reasoning_summary="Inseguro."
    )
    resp2 = LLMResponse(
        provider_id="gemini",
        provider_name="Gemini",
        allocation=AgentAllocation(necessidades=50.0, desejos=30.0, futuro=20.0),
        confidence_score=0.80,
        risk_flags=[],
        reasoning_summary="Seguro."
    )

    converged, max_div = engine.check_convergence([resp1, resp2])
    assert converged is False


def test_deterministic_local_engine():
    """O motor determinístico local deve computar alocação sem erro e retornar status correto."""
    summary = {
        "total_income": 2133.42,
        "fixed_costs": 285.00,
        "debts_total": 1236.83,
        "special_events": 500.00,
        "net_surplus": 111.59
    }

    result = compute_deterministic_local_allocation(summary)
    assert result["consensus_status"] == "deterministico_local"
    assert "necessidades" in result["allocation"]
    assert "desejos" in result["allocation"]
    assert "futuro" in result["allocation"]
    total = sum(result["allocation"].values())
    assert round(total, 0) == 100.0
    assert result["confidence_score"] >= 0.70
    assert len(result["risk_flags"]) > 0


@pytest.mark.asyncio
async def test_schema_retry_logic():
    """Provedor tenta 1 retry quando a resposta inicial não é JSON válido."""
    cb = CircuitBreaker()
    provider = BaseOpenAICompatibleProvider(
        provider_id="mock_groq",
        name="Mock Groq",
        role="Proposer",
        base_url="https://mock.api",
        api_key="valid_dummy_key",
        model="mock-model",
        circuit_breaker=cb
    )

    invalid_json_response = MagicMock()
    invalid_json_response.status_code = 200
    invalid_json_response.json.return_value = {
        "choices": [{"message": {"content": "Isto não é JSON válido"}}]
    }

    valid_json_response = MagicMock()
    valid_json_response.status_code = 200
    valid_json_response.json.return_value = {
        "choices": [{
            "message": {
                "content": '{"allocation": {"necessidades": 50.0, "desejos": 30.0, "futuro": 20.0}, "confidence_score": 0.88, "risk_flags": ["OK"], "reasoning_summary": "Parecer Válido"}'
            }
        }]
    }

    # Primeira chamada falha com json inválido, segunda chamada tem sucesso
    with patch("httpx.AsyncClient.post", side_effect=[invalid_json_response, valid_json_response]) as mock_post:
        resp = await provider.generate("prompt de teste", {})
        assert mock_post.call_count == 2
        assert resp is not None
        assert resp.allocation.necessidades == 50.0
        assert resp.confidence_score == 0.88
        assert resp.reasoning_summary == "Parecer Válido"


@pytest.mark.asyncio
async def test_consensus_loop_ceiling_three_rounds():
    """
    Se os agentes divergirem nas 3 rodadas, o orquestrador para na 3ª rodada,
    seleciona o melhor candidato e marca como 'parcial'.
    """
    engine = ConsensusEngine()
    engine.circuit_breaker = CircuitBreaker()

    # Cria respostas divergentes para todas as rodadas
    def make_divergent_response(pid, name, nec):
        return LLMResponse(
            provider_id=pid,
            provider_name=name,
            allocation=AgentAllocation(necessidades=nec, desejos=20.0, futuro=80.0 - nec),
            confidence_score=0.75,
            risk_flags=["Flag divergente"],
            reasoning_summary=f"Parecer de {name}"
        )

    # Mock dos geradores para que todos respondam mas com divergência
    with patch.object(BaseOpenAICompatibleProvider, "is_configured", return_value=True), \
         patch.object(BaseOpenAICompatibleProvider, "generate") as mock_gen:
        
        mock_gen.side_effect = [
            make_divergent_response("groq", "Groq", 40.0),      # Rodada 1
            make_divergent_response("gemini", "Gemini", 70.0),  # Rodada 1 (diff = 30%)
            make_divergent_response("mistral", "Mistral", 30.0), # Rodada 2
            make_divergent_response("openrouter", "OpenRouter", 80.0), # Rodada 2
            make_divergent_response("cloudflare", "Cloudflare", 50.0)  # Rodada 3
        ]

        summary = {"total_income": 2133.42, "fixed_costs": 285.00, "debts_total": 1236.83, "special_events": 500.00}
        result = await engine.run_consensus_loop(summary, force_recalculate=True)

        assert result.rounds_executed == 3
        assert result.consensus_status == "parcial"
        assert len(result.risk_flags) > 0
