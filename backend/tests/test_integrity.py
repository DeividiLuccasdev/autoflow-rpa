import sqlite3
from types import SimpleNamespace
from sqlalchemy.exc import IntegrityError
from app.integrity import is_duplicate
from test_invoices import client

def test_foreign_key_is_not_duplicate():
    original = sqlite3.IntegrityError("FOREIGN KEY constraint failed")
    original.sqlite_errorname = "SQLITE_CONSTRAINT_FOREIGNKEY"
    assert not is_duplicate(IntegrityError(None, None, original), "invoices", ["id"])

def test_postgres_requires_exact_constraint_and_state():
    original = SimpleNamespace(sqlstate="23505", diag=SimpleNamespace(constraint_name="other_constraint"))
    exc = IntegrityError(None, None, original)
    assert not is_duplicate(exc, "invoices", [], "uq_invoice_identity")
    original.diag.constraint_name = "uq_invoice_identity"
    assert is_duplicate(exc, "invoices", [], "uq_invoice_identity")

def test_unexpected_integrity_is_not_reported_as_duplicate(client, monkeypatch):
    import pytest
    from test_invoices import payload
    http, factory = client
    def fail(*args, **kwargs):
        original = sqlite3.IntegrityError("FOREIGN KEY constraint failed")
        original.sqlite_errorname = "SQLITE_CONSTRAINT_FOREIGNKEY"
        raise IntegrityError(None, None, original)
    monkeypatch.setattr(factory.class_, "flush", fail)
    with pytest.raises(IntegrityError):
        http.post("/api/v1/invoices", json=payload())
