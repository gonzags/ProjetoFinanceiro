"""
test_auth.py - Testes de Autenticação, Hashing, Sessão, CSRF e OAuth (Ledger Horizon)
Valida:
- Hashing PBKDF2-HMAC-SHA256 (600k iterações) e verificação em tempo constante
- Serialização e expiração de cookies de sessão assinados (itsdangerous)
- Proteção CSRF por double-submit cookie vinculado (rejeita tokens forjados ou cookies divergentes)
- Validação estrita de state no OAuth do Google (mitigação de login-CSRF)
- Validação de segurança de SECRET_KEY no boot da aplicação
- Fluxo completo de cadastro (/register), login (/login) e encerramento de sessão (/logout)
- Proteção de rotas e redirecionamento quando ENABLE_AUTH=True
"""

import re
import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

import app as app_module
from app import app
from auth import (
    CSRF_COOKIE_NAME,
    OAUTH_STATE_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    create_oauth_state,
    create_session_token,
    generate_csrf_token,
    hash_password,
    parse_session_token,
    validate_secret_key,
    verify_csrf_token,
    verify_oauth_state,
    verify_password,
)
from utils import db_manager


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def extract_csrf_token(html: str) -> str:
    """Extrai o valor do input csrf_token do formulário HTML."""
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not match:
        match = re.search(r'value="([^"]+)"\s+name="csrf_token"', html)
    assert match, "Token CSRF não encontrado no HTML do formulário."
    return match.group(1)


def test_password_hashing_and_verification():
    """Valida o padrão PBKDF2 600.000 iterações e a verificação defensiva."""
    raw_password = "MinhaSenhaSuperSegura!2026"
    hashed = hash_password(raw_password)

    assert hashed.startswith("pbkdf2:sha256:600000$")
    assert verify_password(raw_password, hashed) is True
    assert verify_password("SenhaIncorreta", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(raw_password, None) is False

    with pytest.raises(ValueError):
        hash_password("")


def test_session_token_lifecycle():
    """Valida a emissão e decodificação do cookie assinado."""
    user_id = 105
    token = create_session_token(user_id)
    assert isinstance(token, str)

    parsed_id = parse_session_token(token)
    assert parsed_id == user_id

    # Token adulterado
    tampered = token + "adulterado"
    assert parse_session_token(tampered) is None
    assert parse_session_token(None) is None


def test_csrf_token_double_submit_lifecycle():
    """Valida a integridade e vínculo do padrão double-submit cookie."""
    token_valid = generate_csrf_token()
    token_attacker = generate_csrf_token()

    # 1. Token no form bate com o cookie do visitante
    assert verify_csrf_token(token_valid, token_valid) is True

    # 2. Token de um atacante enviado com o cookie da vítima -> REJEITADO
    assert verify_csrf_token(token_attacker, token_valid) is False

    # 3. Token sem cookie correspondente -> REJEITADO
    assert verify_csrf_token(token_valid, None) is False
    assert verify_csrf_token(None, token_valid) is False

    # 4. Token corrompido / forjado -> REJEITADO
    assert verify_csrf_token("token_falsificado", "token_falsificado") is False


def test_oauth_state_validation_lifecycle():
    """Valida a geração e conferência do parâmetro state para fluxo OAuth."""
    state_valid = create_oauth_state()
    state_attacker = create_oauth_state()

    assert verify_oauth_state(state_valid, state_valid) is True
    # State do atacante comparado com o cookie da vítima -> REJEITADO
    assert verify_oauth_state(state_attacker, state_valid) is False
    # Ausência de state no cookie ou query -> REJEITADO
    assert verify_oauth_state(state_valid, None) is False
    assert verify_oauth_state(None, state_valid) is False
    assert verify_oauth_state("invalido", "invalido") is False


def test_secret_key_validation_policy(monkeypatch):
    """Garante que a aplicação impeça o boot se SECRET_KEY for insegura quando ENABLE_AUTH=True."""
    # 1. Com ENABLE_AUTH=False: não lança exceção
    validate_secret_key(enable_auth=False)

    # 2. Com ENABLE_AUTH=True e chave default fraca: DEVE FALHAR
    monkeypatch.setenv("ENABLE_AUTH", "True")
    monkeypatch.setenv("SECRET_KEY", "lh-super-secret-key-change-in-production-2026")
    with pytest.raises(RuntimeError) as exc:
        validate_secret_key(enable_auth=True)
    assert "Configuração de Segurança Crítica" in str(exc.value)

    # 3. Com ENABLE_AUTH=True e chave forte e exclusiva: DEVE PASSAR
    monkeypatch.setenv("SECRET_KEY", "u7$9qL!2zX@901_very_secure_random_key_production_2026_xyz")
    validate_secret_key(enable_auth=True)


def test_register_and_login_flow(client):
    """Testa o ciclo de vida completo com validação de double-submit CSRF."""
    # 1. Acessar página de cadastro e obter CSRF token e cookie
    resp_page = client.get("/register")
    assert resp_page.status_code == 200
    assert CSRF_COOKIE_NAME in resp_page.cookies
    csrf_from_cookie = resp_page.cookies[CSRF_COOKIE_NAME]
    csrf_from_form = extract_csrf_token(resp_page.text)
    assert csrf_from_form == csrf_from_cookie

    # 2. Cadastro com dados válidos
    unique_email = f"test_user_{uuid.uuid4().hex[:8]}@ledgerhorizon.local"
    reg_data = {
        "csrf_token": csrf_from_form,
        "name": "Maria Investidora",
        "email": unique_email,
        "password": "senhaForte#2026"
    }
    resp_reg = client.post("/register", data=reg_data, follow_redirects=False)
    assert resp_reg.status_code == 303
    assert resp_reg.headers.get("Location") == "/"
    assert SESSION_COOKIE_NAME in resp_reg.cookies

    # 3. Tentativa de cadastro duplicado deve ser rejeitada com HTTP 400
    resp_dup = client.post("/register", data=reg_data, follow_redirects=False)
    assert resp_dup.status_code == 400
    assert "já está cadastrado" in resp_dup.text

    # 4. Tentativa de ataque CSRF (token de atacante com cookie de vítima) deve falhar com HTTP 400
    foreign_csrf = generate_csrf_token()
    bad_csrf_data = dict(reg_data)
    bad_csrf_data["email"] = "outro@teste.local"
    bad_csrf_data["csrf_token"] = foreign_csrf
    # O cliente envia bad_csrf_data["csrf_token"] mas seu cookie é csrf_from_cookie
    resp_bad_csrf = client.post("/register", data=bad_csrf_data, follow_redirects=False)
    assert resp_bad_csrf.status_code == 400

    # 5. Tentativa de login com senha incorreta
    # Re-obter login page para pegar novo csrf
    resp_lpage = client.get("/login")
    login_csrf = resp_lpage.cookies[CSRF_COOKIE_NAME]
    login_fail_data = {
        "csrf_token": login_csrf,
        "email": unique_email,
        "password": "senhaErrada123"
    }
    resp_fail = client.post("/login", data=login_fail_data, follow_redirects=False)
    assert resp_fail.status_code == 401

    # 6. Login com credenciais válidas e CSRF válido
    resp_lpage2 = client.get("/login")
    login_csrf2 = resp_lpage2.cookies[CSRF_COOKIE_NAME]
    login_success_data = {
        "csrf_token": login_csrf2,
        "email": unique_email,
        "password": "senhaForte#2026"
    }
    resp_login = client.post("/login", data=login_success_data, follow_redirects=False)
    assert resp_login.status_code == 303
    assert SESSION_COOKIE_NAME in resp_login.cookies

    # 7. Logout limpa o cookie
    resp_logout = client.post("/logout", follow_redirects=False)
    assert resp_logout.status_code == 303
    assert resp_logout.headers.get("Location") == "/login"


def test_oauth_google_state_protection(client):
    """Garante que o fluxo OAuth grave o cookie de state e rejeite callbacks sem state legítimo."""
    with patch("app.is_google_auth_configured", return_value=True), \
         patch("app.get_google_auth_url", return_value="https://accounts.google.com/o/oauth2/v2/auth?mock=1"):

        # 1. Iniciar fluxo OAuth deve criar o cookie lh_oauth_state
        resp_oauth = client.get("/auth/google", follow_redirects=False)
        assert resp_oauth.status_code == 303
        assert OAUTH_STATE_COOKIE_NAME in resp_oauth.cookies
        legit_state = resp_oauth.cookies[OAUTH_STATE_COOKIE_NAME]

        # 2. Callback sem cookie de state (Login-CSRF) deve ser rejeitado
        client_no_cookie = TestClient(app)
        resp_bad_state = client_no_cookie.get(
            "/auth/google/callback?code=mock_code&state=fake_state",
            follow_redirects=False
        )
        assert resp_bad_state.status_code == 303
        assert "state+mismatch" in resp_bad_state.headers.get("Location")

        # 3. Callback com cookie mas com state divergente na query string deve ser rejeitado
        resp_mismatch = client.get(
            "/auth/google/callback?code=mock_code&state=outro_state_divergente",
            follow_redirects=False
        )
        assert resp_mismatch.status_code == 303
        assert "state+mismatch" in resp_mismatch.headers.get("Location")


def test_protected_routes_when_enable_auth_true(client, monkeypatch):
    """Garante que quando ENABLE_AUTH=True rotas exigem sessão válida."""
    monkeypatch.setattr(app_module, "ENABLE_AUTH", True)

    # 1. Rota / sem cookie deve redirecionar para /login?next=/
    client_unauth = TestClient(app)
    resp_index = client_unauth.get("/", follow_redirects=False)
    assert resp_index.status_code == 303
    assert "/login?next=/" in resp_index.headers.get("Location")

    # 2. Endpoint /api/kpis sem cookie deve retornar 401
    resp_kpis = client_unauth.get("/api/kpis")
    assert resp_kpis.status_code == 401

    # 3. Criar usuário com onboarding completo e logar
    test_email = "auth_guard_user@horizon.local"
    user = db_manager.demo_manager.create_user(
        email=test_email,
        password_hash=hash_password("senha123"),
        name="Carlos Guard"
    )
    # Marcar onboarding como concluído para que /api/kpis retorne métricas reais
    db_manager.demo_manager.set_onboarding_completed(user["id"])
    session_token = create_session_token(user["id"])

    # 4. Requisições autenticadas devem responder 200
    ac = TestClient(app, cookies={SESSION_COOKIE_NAME: session_token})
    resp_index_auth = ac.get("/")
    assert resp_index_auth.status_code == 200
    # O template exibe o primeiro nome no greeting e no APP_CONFIG
    assert "Carlos" in resp_index_auth.text

    resp_kpis_auth = ac.get("/api/kpis")
    assert resp_kpis_auth.status_code == 200
    kpis_data = resp_kpis_auth.json()
    # Com onboarding concluído, metrics deve ser retornado (não vazio)
    assert "metrics" in kpis_data
    assert not kpis_data.get("empty", False)

