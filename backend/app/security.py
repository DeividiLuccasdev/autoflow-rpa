"""Credencial única para a demonstração local; não substitui usuários/RBAC."""
import os
import secrets
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def check_api_key(key: str | None):
    expected = os.getenv("AUTOFLOW_API_KEY", "")
    if len(expected) < 32:
        raise HTTPException(503, "Configure AUTOFLOW_API_KEY com pelo menos 32 caracteres")
    if key is None or not secrets.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(401, "Credencial inválida")
    return "local-operator"

def require_api_key(key: str | None = Security(api_key_header)):
    return check_api_key(key)
