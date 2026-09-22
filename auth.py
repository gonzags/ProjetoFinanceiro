"""
auth.py - Módulo de Autenticação e Segurança (Ledger Horizon)
Implementa hash de senhas via PBKDF2-HMAC-SHA256 (600.000 iterações, padrão OWASP),
gerenciamento de sessões stateless via cookie assinado (itsdangerous), proteção CSRF
vinculada por double-submit cookie, validação estrita de state no OAuth do Google,
injeção de dependências FastAPI e verificação de segurança no boot da aplicação.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from typing import Any, Dict, Optional
from urllib.parse import quote_plus

import httpx
from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from utils import db_manager

logger = logging.getLogger("ledger_horizon.auth")

# -----------------------------------------------------------------------------
# Configurações de Segurança e Validação de Chaves
# -----------------------------------------------------------------------------
INSECURE_SECRETS = {
    "lh-super-secret-key-change-in-production-2026",
    "lh-substitua-por-uma-chave-aleatoria-em-producao-64bytes",
    "secret",
    "changeme",
    "password",
    "123456"
}

SECRET_KEY = os.getenv("SECRET_KEY", "lh-super-secret-key-change-in-production-2026")
SESSION_COOKIE_NAME = "lh_session"
CSRF_COOKIE_NAME = "lh_csrf"
OAUTH_STATE_COOKIE_NAME = "lh_oauth_state"

SESSION_MAX_AGE_SECONDS = 14 * 24 * 3600  # 14 dias
CSRF_MAX_AGE_SECONDS = 7200               # 2 horas
OAUTH_STATE_MAX_AGE_SECONDS = 300          # 5 minutos
PBKDF2_ITERATIONS = 600_000

# Serializadores seguros para cookies de sessão, tokens CSRF e state OAuth
_session_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="lh_session")
_csrf_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="lh_csrf")
_oauth_state_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="lh_oauth_state")


def validate_secret_key(enable_auth: Optional[bool] = None):
    """
    Se a autenticação estiver habilitada, bloqueia o boot se SECRET_KEY não foi
    configurada ou se mantiver um valor de exemplo público inseguro.
    """
    if enable_auth is None:
        enable_auth = os.getenv("ENABLE_AUTH", "False").lower() in ("true", "1", "yes")

    if enable_auth:
        sk = os.getenv("SECRET_KEY")
        if not sk or sk.strip() in INSECURE_SECRETS:
            raise RuntimeError(
                "Configuração de Segurança Crítica: ENABLE_AUTH está ativado, mas SECRET_KEY "
                "não foi configurada ou utiliza um valor de exemplo público inseguro. "
                "Defina uma SECRET_KEY forte e exclusiva no arquivo .env para iniciar a aplicação."
            )


# -----------------------------------------------------------------------------
# Hashing de Senhas (PBKDF2-HMAC-SHA256)
# -----------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """
    Gera hash seguro com salt aleatório de 16 bytes e 600.000 iterações de SHA-256.
    Formato: pbkdf2:sha256:600000$<salt_hex>$<hash_hex>
    """
    if not password:
        raise ValueError("Senha não pode ser vazia.")
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2:sha256:{PBKDF2_ITERATIONS}${salt.hex()}${key.hex()}"


def verify_password(password: str, hashed_value: Optional[str]) -> bool:
    """
    Valida a senha contra o hash armazenado usando comparação em tempo constante.
    Trata contas Google (password_hash=None) com segurança.
    """
    if not password or not hashed_value:
        return False

    try:
        parts = hashed_value.split("$")
        if len(parts) != 3:
            return False

        algo_iter, salt_hex, hash_hex = parts
        _, _, iter_str = algo_iter.split(":")
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)

        computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(computed, expected_hash)
    except Exception as e:
        logger.warning(f"Erro ao verificar senha: {e}")
        return False


# -----------------------------------------------------------------------------
# Tokens de Sessão Assinados (itsdangerous)
# -----------------------------------------------------------------------------
def create_session_token(user_id: int) -> str:
    """Cria um token assinado contendo o user_id."""
    return _session_serializer.dumps({"user_id": user_id})


def parse_session_token(token: Optional[str]) -> Optional[int]:
    """
    Valida e extrai o user_id do token de sessão.
    Retorna None se o token for inválido, adulterado ou expirado (>14 dias).
    """
    if not token:
        return None
    try:
        data = _session_serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return data.get("user_id")
    except (BadSignature, SignatureExpired):
        return None
    except Exception as e:
        logger.warning(f"Erro inesperado ao decodificar token de sessão: {e}")
        return None


# -----------------------------------------------------------------------------
# Proteção CSRF Vinculada à Sessão (Double-Submit Cookie Criptografado)
# -----------------------------------------------------------------------------
def generate_csrf_token() -> str:
    """Gera um token CSRF assinado com payload aleatório temporal."""
    random_nonce = secrets.token_hex(16)
    return _csrf_serializer.dumps({"nonce": random_nonce})


def verify_csrf_token(token_from_form: Optional[str], token_from_cookie: Optional[str]) -> bool:
    """
    Valida se o token CSRF enviado no formulário bate exatamente com o cookie do visitante
    (double-submit pattern) e se a assinatura criptográfica e tempo de expiração são válidos.
    """
    if not token_from_form or not token_from_cookie:
        return False

    # Comparação em tempo constante para mitigar timing attacks
    if not hmac.compare_digest(token_from_form.strip(), token_from_cookie.strip()):
        return False

    try:
        data = _csrf_serializer.loads(token_from_form, max_age=CSRF_MAX_AGE_SECONDS)
        return "nonce" in data
    except (BadSignature, SignatureExpired):
        return False
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Validação de State do OAuth 2.0 (Mitigação de Login-CSRF)
# -----------------------------------------------------------------------------
def create_oauth_state() -> str:
    """Gera um token de state assinado com validade de 5 minutos."""
    nonce = secrets.token_hex(16)
    return _oauth_state_serializer.dumps({"oauth_nonce": nonce})


def verify_oauth_state(state_from_query: Optional[str], state_from_cookie: Optional[str]) -> bool:
    """
    Valida o parâmetro state recebido no callback do OAuth comparando-o com o gravado no cookie.
    Impede ataques de login-CSRF e account linking forçado.
    """
    if not state_from_query or not state_from_cookie:
        return False

    if not hmac.compare_digest(state_from_query.strip(), state_from_cookie.strip()):
        return False

    try:
        data = _oauth_state_serializer.loads(state_from_query, max_age=OAUTH_STATE_MAX_AGE_SECONDS)
        return "oauth_nonce" in data
    except (BadSignature, SignatureExpired):
        return False
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Dependências de Usuário (FastAPI)
# -----------------------------------------------------------------------------
async def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Obtém o usuário autenticado a partir do cookie de sessão.
    Retorna None se não autenticado.
    """
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie_token:
        return None

    user_id = parse_session_token(cookie_token)
    if not user_id:
        return None

    user = await db_manager.get_user_by_id(user_id)
    return user


async def require_user_api(request: Request) -> Dict[str, Any]:
    """Garante autenticação para endpoints de API. Retorna HTTP 401 se ausente."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação obrigatória. Por favor, efetue login."
        )
    return user


async def require_user_web(request: Request) -> Dict[str, Any]:
    """Garante autenticação para rotas HTML. Redireciona para /login se ausente."""
    user = await get_current_user(request)
    if not user:
        next_path = quote_plus(request.url.path)
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/login?next={next_path}"}
        )
    return user


# -----------------------------------------------------------------------------
# Google OAuth 2.0 (Defensivo)
# -----------------------------------------------------------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")


def is_google_auth_configured() -> bool:
    """Verifica se credenciais do Google OAuth estão presentes."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def get_google_auth_url(redirect_uri: str, state: str) -> str:
    """Constrói a URL de autorização do Google."""
    if not is_google_auth_configured():
        raise RuntimeError("Google OAuth não está configurado.")
    
    encoded_redirect = quote_plus(redirect_uri)
    encoded_scope = quote_plus("openid email profile")
    return (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?response_type=code"
        f"&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={encoded_redirect}"
        f"&scope={encoded_scope}"
        f"&state={state}"
        f"&access_type=online"
    )


async def exchange_google_code_for_user(code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
    """
    Troca o authorization code por tokens e obtém as informações do perfil do usuário.
    Retorna dicionário com 'email', 'name', 'sub' ou None se falhar.
    """
    if not is_google_auth_configured():
        logger.warning("Tentativa de login Google OAuth sem credenciais configuradas.")
        return None

    token_url = "https://oauth2.googleapis.com/token"
    userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"

    payload = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(token_url, data=payload)
            if token_resp.status_code != 200:
                logger.error(f"Erro ao trocar código por token Google: {token_resp.status_code} {token_resp.text}")
                return None
            tokens = token_resp.json()
            access_token = tokens.get("access_token")
            if not access_token:
                return None

            userinfo_resp = await client.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if userinfo_resp.status_code != 200:
                logger.error(f"Erro ao obter userinfo Google: {userinfo_resp.status_code} {userinfo_resp.text}")
                return None
            user_data = userinfo_resp.json()
            return {
                "email": user_data.get("email"),
                "name": user_data.get("name", "Usuário Google"),
                "sub": user_data.get("sub"),
            }
    except Exception as e:
        logger.error(f"Exceção durante fluxo Google OAuth: {e}")
        return None
