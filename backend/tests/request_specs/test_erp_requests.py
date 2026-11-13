"""describe ERP fictício: formulário HTTP e SQLite temporário reais."""

import sqlite3

import pytest
from fastapi.testclient import TestClient
from helpers import payload, simultaneous

from simulators.erp import app


@pytest.fixture
def erp(tmp_path, monkeypatch):
    path = tmp_path / "erp_test.sqlite"
    monkeypatch.setenv("RPA_SIM_DB", str(path))
    with TestClient(app, follow_redirects=False) as http:
        yield http, path


def test_quando_salva_e_recarrega_entao_um_lancamento(erp):
    http, path = erp
    response = http.post("/invoices", data=payload())
    assert response.status_code == 303
    for _ in range(2):
        assert http.get(response.headers["location"]).status_code == 200
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 1


def test_quando_dois_formularios_simultaneos_entao_um_lancamento(erp):
    http, path = erp
    responses = simultaneous(*[lambda: http.post("/invoices", data=payload()) for _ in range(2)])
    assert sorted(r.status_code for r in responses) == [303, 409]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 1


@pytest.mark.parametrize("amount", ["0", "-1", "1.001"])
def test_quando_valor_invalido_entao_nao_salva(erp, amount):
    http, path = erp
    assert http.post("/invoices", data=payload(amount=amount)).status_code == 422
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 0
