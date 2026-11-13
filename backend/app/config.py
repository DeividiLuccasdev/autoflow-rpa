"""Configuração central lida das variáveis de ambiente.

Os valores são lidos a cada acesso, e não uma única vez na importação, para que
testes e scripts possam alterar o ambiente em tempo de execução.
"""

import os
from pathlib import Path

from starlette.requests import Request

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() == "true"


class Settings:
    @property
    def database_url(self) -> str:
        """URL SQLAlchemy; aceita o formato postgres:// fornecido por provedores como o Render."""
        url = os.getenv("DATABASE_URL", "sqlite:///./autoflow.db")
        if url.startswith(("postgres://", "postgresql://")):
            url = "postgresql+psycopg://" + url.split("://", 1)[1]
        return url

    @property
    def redis_url(self) -> str:
        return os.getenv("REDIS_URL", "redis://localhost:6379/0")

    @property
    def api_key(self) -> str:
        """Chave operacional do acervo legado e da emissão de convites."""
        return os.getenv("AUTOFLOW_API_KEY", "")

    @property
    def async_enabled(self) -> bool:
        """Desativado no Render gratuito, que não tem worker nem Redis."""
        return _flag("AUTOFLOW_ASYNC_ENABLED", True)

    @property
    def behind_https_proxy(self) -> bool:
        """O Render termina o TLS no proxy; a aplicação recebe HTTP internamente."""
        return os.getenv("RENDER") == "true"


settings = Settings()


def is_secure(request: Request) -> bool:
    """Indica se cookies devem ser marcados como Secure e se o HSTS deve ser enviado."""
    return request.url.scheme == "https" or settings.behind_https_proxy
