"""Proteções HTTP e limites locais para o demo de um único processo."""
from collections import OrderedDict, deque
from threading import Lock
from time import monotonic
import os
from fastapi import HTTPException
from starlette.responses import JSONResponse
from .security import authenticate_scope
from starlette.concurrency import run_in_threadpool

class SlidingLimiter:
    def __init__(self):
        self.buckets = OrderedDict()
        self.lock = Lock()

    def clear(self):
        with self.lock:
            self.buckets.clear()

    def allow(self, peer, group, maximum):
        now = monotonic()
        with self.lock:
            for key in list(self.buckets):
                values = self.buckets[key]
                while values and now - values[0] >= 60:
                    values.popleft()
                if not values:
                    del self.buckets[key]
            key = (peer, group)
            if key not in self.buckets:
                if len(self.buckets) >= 2048:
                    return False
                self.buckets[key] = deque()
            values = self.buckets[key]
            if len(values) >= maximum:
                return False
            values.append(now)
            return True

limiter = SlidingLimiter()

class HttpSecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        headers = dict(scope.get("headers", []))
        async def protected_send(message):
            if message["type"] == "http.response.start":
                values = list(message.get("headers", []))
                # Swagger precisa do inicializador inline; a página principal não.
                swagger = path in {"/docs", "/redoc", "/docs/oauth2-redirect"}
                script = "'self' https://cdn.jsdelivr.net 'unsafe-inline'" if swagger else "'self'"
                csp = f"default-src 'self'; script-src {script}; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'"
                values.extend([(b"content-security-policy", csp.encode()), (b"x-frame-options", b"DENY"),
                               (b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
                               (b"permissions-policy", b"camera=(), microphone=(), geolocation=()")])
                if path.startswith(("/api/", "/demo/", "/auth/")) or path == "/workspace":
                    values.append((b"cache-control", b"no-store"))
                elif path == "/":
                    values.append((b"cache-control", b"no-cache"))
                if scope.get("scheme") == "https" or os.getenv("RENDER") == "true":
                    values.append((b"strict-transport-security", b"max-age=31536000"))
                message = {**message, "headers": values}
            await send(message)

        # Não confia em X-Forwarded-For fornecido pelo cliente.
        peer = (scope.get("client") or ("unknown", 0))[0]
        group, maximum = None, 0
        if path.startswith("/api/v1/"):
            group, maximum = "private", 60
        elif path in {"/auth/login", "/auth/register"}:
            group, maximum = "login", 10
        elif path.startswith("/auth/"):
            group, maximum = "private", 60
        elif path == "/demo/analyze" or path == "/demo/automation/runs":
            group, maximum = "demo-create", 15
        elif path.startswith("/demo/automation/"):
            group, maximum = "demo-advance", 90
        if group and not limiter.allow(peer, group, maximum):
            return await JSONResponse({"detail": "Limite temporário de requisições; aguarde um minuto"}, status_code=429, headers={"Retry-After": "60"})(scope, receive, protected_send)

        # Autentica antes de receber e armazenar corpos de uploads privados.
        if path.startswith("/api/v1/") or path in {"/auth/me", "/auth/logout", "/auth/invitations"}:
            try:
                identity = await run_in_threadpool(authenticate_scope, scope, headers)
                scope.setdefault("state", {})["identity"] = identity
            except HTTPException as exc:
                return await JSONResponse({"detail": exc.detail}, status_code=exc.status_code)(scope, receive, protected_send)
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = headers.get(b"origin")
            host = headers.get(b"host", b"")
            if origin:
                from urllib.parse import urlsplit
                try:
                    parsed = urlsplit(origin.decode("latin-1"))
                    allowed = parsed.netloc.encode("latin-1") == host and parsed.scheme in {"https", "http"}
                except ValueError:
                    allowed = False
                if not allowed:
                    return await JSONResponse({"detail": "Origem não permitida"}, status_code=403)(scope, receive, protected_send)
        await self.app(scope, receive, protected_send)
