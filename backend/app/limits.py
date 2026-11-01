"""Limita o corpo antes do parser multipart, inclusive sem Content-Length."""
import asyncio
import time
from starlette.responses import JSONResponse

class BodyLimitMiddleware:
    def __init__(self, app, limit=5 * 1024 * 1024 + 65536):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        chunks, total = [], 0
        deadline = time.monotonic() + 30
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=max(0.001, min(15, deadline - time.monotonic())))
            except asyncio.TimeoutError:
                return await JSONResponse({"detail": "Tempo de upload excedido"}, status_code=408)(scope, receive, send)
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.limit:
                return await JSONResponse({"detail": "Corpo da requisição excede o limite"}, status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()
        await self.app(scope, bounded_receive, send)
