"""
test_api_endpoints.py - Testes de integração dos Endpoints FastAPI (TestClient)
Valida:
- Rota principal / e renderização de templates
- Endpoints REST (/api/status, /api/kpis, /api/timeline, /api/consensus)
- Invalidação de cache ao enviar dados via /api/questionnaire
- Seletor de metodologias (/api/methodology)
- Rate limiting estrito em /api/consensus/recalculate
- Headers de segurança HTTP
"""

import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app
from utils import db_manager


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def force_auth_off(monkeypatch):
    """Desativa ENABLE_AUTH para todos os testes deste módulo — auth é testado em test_auth.py."""
    monkeypatch.setattr(app_module, "ENABLE_AUTH", False)


def test_index_page_rendered(client):
    """A página principal deve retornar 200 e carregar o Design Ledger Horizon."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Ledger Horizon" in resp.text
    # Headers de segurança
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"


def test_api_status(client):
    """Endpoint de status do sistema deve reportar estado do data warehouse / demo."""
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status_badge" in data
    assert "is_connected" in data


def test_health_endpoint(client):
    """Endpoint /health deve responder 200 ok para o Docker Healthcheck."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api_kpis(client):
    """Sem usuário autenticado, /api/kpis retorna estado vazio (sem seed data)."""
    resp = client.get("/api/kpis?month=Outubro")
    assert resp.status_code == 200
    data = resp.json()
    # Com o guard de onboarding, retorna empty=True e sem dados de seed
    assert data.get("empty") is True
    assert data["summary"] == {}
    assert data["metrics"] == {}


def test_api_timeline(client):
    """Timeline deve conter projeções de meses futuros."""
    resp = client.get("/api/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    assert "month" in data[0]
    assert "status_label" in data[0]


def test_api_methodology_selector(client):
    """Seletor de metodologias deve calcular corretamente as cotas."""
    # 50-30-20
    resp = client.post("/api/methodology", json={"methodology": "50-30-20", "income": 2000.0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["percentages"]["necessidades"] == 50.0
    assert data["allocations"]["necessidades"] == 1000.0

    # 60-20-20
    resp2 = client.post("/api/methodology", json={"methodology": "60-20-20", "income": 2000.0})
    assert resp2.status_code == 200
    assert resp2.json()["percentages"]["necessidades"] == 60.0

    # Base Zero
    resp3 = client.post("/api/methodology", json={"methodology": "zero_based", "income": 2000.0})
    assert resp3.status_code == 200
    assert "reserva_disponivel" in resp3.json()["allocations"]


def test_api_questionnaire_and_cache_invalidation(client):
    """Atualizar o questionário deve invalidar o cache ativo de consenso e salvar todos os campos."""
    # Garante que há um cache
    client.get("/api/consensus?month=Outubro")

    # Envia atualização completa incluindo custos fixos e compromissos pontuais
    update_payload = {
        "salary_net": 1900.00,
        "fixed_expenses": [
            {"name": "Academia", "amount": 170.0, "category": "Saúde"},
            {"name": "Internet", "amount": 100.0, "category": "Conectividade"}
        ],
        "one_off_commitments": [
            {"name": "Viagem", "amount": 400.0, "month": "Outubro"},
            {"name": "Quitação amigo", "amount": 70.0, "month": "Outubro"}
        ]
    }
    resp = client.post("/api/questionnaire", json=update_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["updated_summary"]["salary_net"] == 1900.00
    assert data["updated_summary"]["fixed_costs"] == 270.00
    assert data["updated_summary"]["special_events"] == 470.00

    # Cache deve ter sido invalidado no gerenciador
    active_cache = db_manager.demo_manager.get_active_cache(max_age_hours=24)
    assert active_cache is None


def test_recalculate_consensus_rate_limiting(client):
    """O endpoint /api/consensus/recalculate deve permitir até 3 chamadas e bloquear a 4ª com HTTP 429."""
    # Chamada 1
    r1 = client.post("/api/consensus/recalculate?month=Outubro")
    assert r1.status_code == 200
    # Chamada 2
    r2 = client.post("/api/consensus/recalculate?month=Outubro")
    assert r2.status_code == 200
    # Chamada 3
    r3 = client.post("/api/consensus/recalculate?month=Outubro")
    assert r3.status_code == 200
    # Chamada 4 - Deve estourar o limite de 3/hora por IP
    r4 = client.post("/api/consensus/recalculate?month=Outubro")
    assert r4.status_code == 429


def test_enable_auth_toggle_behavior(client, monkeypatch):
    """Verifica a alternância de comportamento entre ENABLE_AUTH=False e ENABLE_AUTH=True."""
    # 1. Com ENABLE_AUTH=False (padrão): rota / é pública
    monkeypatch.setattr(app_module, "ENABLE_AUTH", False)
    resp_false = client.get("/", follow_redirects=False)
    assert resp_false.status_code == 200

    # 2. Com ENABLE_AUTH=True: rota / redireciona para login
    monkeypatch.setattr(app_module, "ENABLE_AUTH", True)
    resp_true = client.get("/", follow_redirects=False)
    assert resp_true.status_code == 303
    assert "/login" in resp_true.headers.get("Location")
