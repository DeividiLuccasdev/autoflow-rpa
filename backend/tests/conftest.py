"""Fixtures compartilhadas pelos testes rápidos (SQLite em memória)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture
def client(monkeypatch):
    from app.http_security import limiter

    limiter.clear()
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
