import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app
from app.models import AuditEvent

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTOFLOW_API_KEY", "test-key-" + "x" * 40)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def override():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        client.headers["X-API-Key"] = "test-key-" + "x" * 40
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()

def payload(**changes):
    return {"issuer_cnpj": "12.345.678/0001-95", "number": "00042", "series": "01", "amount": "123.45", **changes}

def test_create_and_audit(client):
    http, _ = client
    response = http.post("/api/v1/invoices", json=payload())
    assert response.status_code == 201
    data = response.json()
    assert data["number"] == "42"
    assert data["amount"] == "123.45"
    assert data["status"] == "validated"
    assert http.get(f'/api/v1/invoices/{data["id"]}/events').json()[0]["event"] == "invoice.validated"

def test_duplicate_normalized_identity_is_atomic(client):
    http, factory = client
    assert http.post("/api/v1/invoices", json=payload()).status_code == 201
    assert http.post("/api/v1/invoices", json=payload(issuer_cnpj="12345678000195", number="42", series="1")).status_code == 409
    assert len(http.get("/api/v1/invoices").json()) == 1
    with factory() as session:
        assert len(session.scalars(select(AuditEvent)).all()) == 1

@pytest.mark.parametrize("changes", [{"amount": "0"}, {"amount": "-1"}, {"amount": "1.001"}, {"issuer_cnpj": "11111111111111"}, {"issuer_cnpj": "12345678000100"}, {"number": "abc"}])
def test_invalid_data(client, changes):
    http, _ = client
    assert http.post("/api/v1/invoices", json=payload(**changes)).status_code == 422
    assert http.get("/api/v1/invoices").json() == []

def test_missing_invoice(client):
    assert client[0].get("/api/v1/invoices/missing/events").status_code == 404
