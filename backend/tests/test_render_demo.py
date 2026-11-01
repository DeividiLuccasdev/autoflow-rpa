from sqlalchemy import select
from app.models import Execution
from test_invoices import client
from test_documents import pdf

def test_demo_does_not_queue_without_worker(client, monkeypatch):
    monkeypatch.setenv("AUTOFLOW_ASYNC_ENABLED", "false")
    http, factory = client
    response = http.post("/api/v1/executions", files={"file": ("nota.pdf", pdf(), "application/pdf")})
    assert response.status_code == 503
    with factory() as db:
        assert db.scalar(select(Execution)) is None
    response = http.post("/api/v1/invoices/upload", files={"file": ("nota.pdf", pdf(), "application/pdf")})
    assert response.status_code == 201

def test_readiness_checks_database(client):
    assert client[0].get("/ready").json() == {"status": "ready"}

def test_readiness_failure_does_not_leak_details(client, monkeypatch):
    http, factory = client
    def failure(*args, **kwargs):
        raise RuntimeError("secret-database-password")
    monkeypatch.setattr(factory.class_, "execute", failure)
    response = http.get("/ready")
    assert response.status_code == 503
    assert "secret" not in response.text
