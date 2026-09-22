"""
test_onboarding.py - Testes do Wizard de Onboarding e Isolamento Multi-Tenant
Valida:
- Salvamento de rascunho (is_draft=True) mantendo onboarding_completed=False
- Conclusão final (is_draft=False) marcando onboarding_completed=True e invalidando cache
- Persistência e recuperação de rascunho (/api/onboarding)
- Isolamento estrito de dados e KPIs entre usuários diferentes (Multi-Tenant)
"""

import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app
from auth import SESSION_COOKIE_NAME, create_session_token, hash_password
from utils import db_manager


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _authed_client(token: str) -> TestClient:
    """Retorna um TestClient com o cookie de sessão pré-configurado na instância."""
    return TestClient(app, cookies={SESSION_COOKIE_NAME: token})


def test_onboarding_draft_preserves_incomplete_flag(client, monkeypatch):
    """Salvar rascunho deve persistir os dados mas MANTER onboarding_completed=False."""
    monkeypatch.setattr(app_module, "ENABLE_AUTH", True)

    user = db_manager.demo_manager.create_user(
        email="draft_user@horizon.local",
        password_hash=hash_password("senha123"),
        name="Lucas Rascunho"
    )
    user_id = user["id"]
    token = create_session_token(user_id)
    ac = _authed_client(token)

    assert user["onboarding_completed"] is False

    # Envia rascunho com respostas parciais (Passos 1 e 2)
    draft_payload = {
        "is_draft": True,
        "name": "Lucas Rascunho",
        "age": 30,
        "occupation": "Arquiteto de Soluções",
        "monthly_income": 8500.00,
        "extra_income": 1000.00,
        "fixed_expenses_val": 2500.00,
        "variable_expenses_val": 1500.00
    }
    resp = ac.post("/api/onboarding", json=draft_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["is_draft"] is True
    assert data["onboarding_completed"] is False

    # Confirma que o usuário continua com onboarding_completed=False
    recheck_user = db_manager.demo_manager.get_user_by_id(user_id)
    assert recheck_user["onboarding_completed"] is False

    # GET /api/onboarding deve retornar o rascunho para reabertura no modal
    resp_get = ac.get("/api/onboarding")
    assert resp_get.status_code == 200
    profile_data = resp_get.json()["profile"]
    assert profile_data["occupation"] == "Arquiteto de Soluções"
    assert profile_data["monthly_income"] == 8500.00


def test_onboarding_final_submission_completes_profile(client, monkeypatch):
    """A conclusão final deve marcar onboarding_completed=True e atualizar o resumo financeiro."""
    monkeypatch.setattr(app_module, "ENABLE_AUTH", True)

    user = db_manager.demo_manager.create_user(
        email="final_user@horizon.local",
        password_hash=hash_password("senha123"),
        name="Beatriz Final"
    )
    user_id = user["id"]
    token = create_session_token(user_id)
    ac = _authed_client(token)

    full_payload = {
        "is_draft": False,
        "name": "Beatriz Final",
        "age": 34,
        "occupation": "Médica",
        "monthly_income": 15000.00,
        "extra_income": 2000.00,
        "fixed_expenses_val": 4000.00,
        "variable_expenses_val": 3000.00,
        "saved_amount": 50000.00,
        "saved_destination": "aposentadoria",
        "invests": "ja_investe_regular",
        "investment_types": ["renda_fixa", "acoes_fiis"],
        "risk_tolerance": "moderado"
    }

    resp = ac.post("/api/onboarding", json=full_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["is_draft"] is False
    assert data["onboarding_completed"] is True

    # Confirma flag True no usuário
    updated_user = db_manager.demo_manager.get_user_by_id(user_id)
    assert updated_user["onboarding_completed"] is True

    # Verifica se os KPIs do usuário refletem seus próprios números
    resp_kpis = ac.get("/api/kpis")
    assert resp_kpis.status_code == 200
    summary = resp_kpis.json()["summary"]
    assert summary["salary_net"] == 15000.00
    assert summary["fixed_costs"] == 4000.00


def test_onboarding_multi_tenant_profile_isolation(client, monkeypatch):
    """Garante que dados do Usuário A não vazam nem afetam o Usuário B."""
    monkeypatch.setattr(app_module, "ENABLE_AUTH", True)

    # Usuário Alfa: R$ 4.000 de salário
    user_a = db_manager.demo_manager.create_user(
        email="user_a_iso@horizon.local",
        password_hash=hash_password("senha123"),
        name="Usuário Alfa"
    )
    ac_a = _authed_client(create_session_token(user_a["id"]))
    ac_a.post(
        "/api/onboarding",
        json={"is_draft": False, "name": "Usuário Alfa", "monthly_income": 4000.0, "fixed_expenses_val": 1200.0},
    )

    # Usuário Beta: R$ 25.000 de salário
    user_b = db_manager.demo_manager.create_user(
        email="user_b_iso@horizon.local",
        password_hash=hash_password("senha123"),
        name="Usuário Beta"
    )
    ac_b = _authed_client(create_session_token(user_b["id"]))
    ac_b.post(
        "/api/onboarding",
        json={"is_draft": False, "name": "Usuário Beta", "monthly_income": 25000.0, "fixed_expenses_val": 6000.0},
    )

    # Verificar KPIs de A
    resp_a = ac_a.get("/api/kpis")
    assert resp_a.status_code == 200
    assert resp_a.json()["summary"]["salary_net"] == 4000.0
    assert resp_a.json()["summary"]["fixed_costs"] == 1200.0
    assert resp_a.json()["metrics"]["user_display_name"] == "Usuário Alfa"

    # Verificar KPIs de B
    resp_b = ac_b.get("/api/kpis")
    assert resp_b.status_code == 200
    assert resp_b.json()["summary"]["salary_net"] == 25000.0
    assert resp_b.json()["summary"]["fixed_costs"] == 6000.0
    assert resp_b.json()["metrics"]["user_display_name"] == "Usuário Beta"


def test_timeline_isolation_without_prior_kpis_call(client, monkeypatch):
    """Garante que /api/timeline não caia no fallback de seed data mesmo sendo chamado isoladamente."""
    monkeypatch.setattr(app_module, "ENABLE_AUTH", True)

    user = db_manager.demo_manager.create_user(
        email="timeline_iso_user@horizon.local",
        password_hash=hash_password("senha123"),
        name="Camila Timeline"
    )
    token = create_session_token(user["id"])
    ac = _authed_client(token)

    # Cadastra perfil via onboarding com salário de 9000 e fixed de 3000
    ac.post(
        "/api/onboarding",
        json={"is_draft": False, "name": "Camila Timeline", "monthly_income": 9000.0, "fixed_expenses_val": 3000.0},
    )

    # Limpar qualquer cache em memória simulando um novo processo/worker
    # Chama diretamente /api/timeline SEM ter chamado /api/kpis antes
    resp_tl = ac.get("/api/timeline")
    assert resp_tl.status_code == 200
    timeline = resp_tl.json()
    assert len(timeline) == 11
    # Deve refletir o salário de Camila (9000), não de Pedro Silva (1843.42)
    assert timeline[0]["total_income"] == 9000.0
    assert timeline[0]["fixed_costs"] == 3000.0
