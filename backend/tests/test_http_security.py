import asyncio
from uuid import uuid4
import pytest
from app.http_security import SlidingLimiter
from app.demo_automation import create_run, context, lock, sessions
from test_invoices import client

def test_browser_headers_and_scoped_csp(client):
    http, _ = client
    response = http.get("/")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "script-src 'self';" in response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "https://cdn.jsdelivr.net" in http.get("/docs").headers["Content-Security-Policy"]
    assert http.get("/api/v1/invoices").headers["Cache-Control"] == "no-store"

@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://[invalid"])
def test_cross_origin_mutation_blocked(client, origin):
    response = client[0].post("/demo/automation/runs", headers={"Origin": origin, "X-Demo-Session": str(uuid4())})
    assert response.status_code == 403

def test_same_origin_allowed(client):
    response = client[0].post("/demo/automation/runs", headers={"Origin": "http://testserver", "X-Demo-Session": str(uuid4())})
    assert response.status_code == 201

def test_demo_request_limit_and_spoofed_forwarded_for(client):
    http, _ = client
    for i in range(15):
        assert http.post("/demo/automation/runs", headers={"X-Demo-Session": str(uuid4()), "X-Forwarded-For": f"192.0.2.{i}"}).status_code == 201
    response = http.post("/demo/automation/runs", headers={"X-Demo-Session": str(uuid4()), "X-Forwarded-For": "203.0.113.99"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"

def test_private_auth_happens_before_upload_body():
    from app.http_security import HttpSecurityMiddleware, limiter
    import os
    from unittest.mock import patch
    async def scenario():
        async def forbidden(*args):
            raise AssertionError("Corpo não deve ser lido nem encaminhado")
        messages = []
        async def send(message):
            messages.append(message)
        scope = {"type":"http", "method":"POST", "path":"/api/v1/invoices/upload", "headers":[], "client":("auth-test",0), "scheme":"http"}
        await HttpSecurityMiddleware(forbidden)(scope, forbidden, send)
        assert messages[0]["status"] == 401
    limiter.clear()
    with patch.dict(os.environ, {"AUTOFLOW_API_KEY": "x" * 40}):
        asyncio.run(scenario())

def test_public_body_limit_before_pdf_parse(client):
    assert client[0].post("/demo/analyze", content=b"x" * 131073).status_code == 413

def test_unknown_run_does_not_allocate_session():
    session_id = uuid4()
    with lock:
        before = len(sessions)
        with pytest.raises(Exception) as error:
            context(session_id)
        assert error.value.status_code == 404
        assert str(session_id) not in sessions

def test_full_session_store_does_not_evict_active_state(monkeypatch):
    import app.demo_automation as module
    from collections import OrderedDict
    monkeypatch.setattr(module, "sessions", OrderedDict())
    monkeypatch.setattr(module, "MAX_SESSIONS", 1)
    first_id = uuid4()
    first = create_run(first_id)
    with pytest.raises(Exception) as error:
        create_run(uuid4())
    assert error.value.status_code == 429
    assert first["id"] in module.sessions[str(first_id)]["runs"]

def test_limiter_memory_is_bounded():
    limiter = SlidingLimiter()
    for i in range(2048):
        assert limiter.allow(str(i), "demo", 1)
    assert not limiter.allow("new-peer", "demo", 1)
    assert len(limiter.buckets) == 2048
