"""Sessões individuais; a chave operacional acessa somente o acervo legado."""

import hashlib
import secrets
from datetime import UTC, datetime
from http.cookies import SimpleCookie

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select

from .config import settings
from .db import get_db
from .models import LoginSession, User

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
    return f"pbkdf2_sha256$600000${salt}${derived}"


def verify_password(password, encoded):
    try:
        _, _, salt, _ = encoded.split("$")
        return secrets.compare_digest(password_hash(password, salt), encoded)
    except (ValueError, TypeError):
        return False


def check_api_key(key: str | None):
    expected = settings.api_key
    if len(expected) < 32:
        raise HTTPException(503, "Configure AUTOFLOW_API_KEY com pelo menos 32 caracteres")
    if key is None or not secrets.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(401, "Credencial inválida")
    return "local-operator"


def current_identity(request: Request, key: str | None = Security(api_key_header)):
    """Identidade autenticada pelo HttpSecurityMiddleware: sessão individual ou chave do acervo legado.

    O parâmetro `key` só existe para o Swagger exibir o botão Authorize com X-API-Key.
    """
    return request.state.identity


def authenticate_scope(scope, headers):
    """Valida antes do upload; usa a mesma conexão real injetada nas rotas."""
    key = headers.get(b"x-api-key")
    if key:
        check_api_key(key.decode("latin-1"))
        return {"owner_id": "legacy", "actor": "local-operator", "legacy": True}
    cookies = SimpleCookie()
    try:
        cookies.load(headers.get(b"cookie", b"").decode("latin-1"))
    except Exception:
        raise HTTPException(401, "Sessão inválida") from None
    cookie = cookies.get("autoflow_session")
    if not cookie:
        # Conserva o diagnóstico de configuração do acesso legado.
        check_api_key(None)
    token = cookie.value
    if len(token) > 128:
        raise HTTPException(401, "Sessão inválida")
    provider = scope["app"].dependency_overrides.get(get_db, get_db)
    generator = provider()
    try:
        db = next(generator)
        session = db.scalar(
            select(LoginSession).where(
                LoginSession.token_hash == digest(token), LoginSession.expires_at > datetime.now(UTC)
            )
        )
        user = db.get(User, session.user_id) if session else None
        if not user:
            raise HTTPException(401, "Sessão inválida ou expirada")
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            csrf = headers.get(b"x-csrf-token", b"").decode("latin-1")
            if not secrets.compare_digest(csrf, session.csrf_token):
                raise HTTPException(403, "Token de proteção inválido")
        return {
            "owner_id": user.id,
            "actor": user.id,
            "email": user.email,
            "legacy": False,
            "csrf_token": session.csrf_token,
            "session_hash": session.token_hash,
        }
    finally:
        generator.close()
