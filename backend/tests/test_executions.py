from datetime import UTC

from sqlalchemy import select
from test_documents import pdf
from test_invoices import payload

from app.executions import process_execution
from app.models import AuditEvent, Document, Execution, Invoice


def submit(http, content):
    return http.post("/api/v1/executions", files={"file": ("demo.pdf", content, "application/pdf")})


def test_queue_process_and_redelivery(client):
    http, factory = client
    content = pdf()
    response = submit(http, content)
    assert response.status_code == 202
    execution_id = response.json()["id"]
    assert response.json()["status"] == "queued"
    assert submit(http, content).json()["id"] == execution_id
    with factory() as db:
        process_execution(db, execution_id)
        process_execution(db, execution_id)
        assert len(db.scalars(select(Invoice)).all()) == 1
        assert len(db.scalars(select(Document)).all()) == 1
        assert len(db.scalars(select(AuditEvent)).all()) == 2
    result = http.get(f"/api/v1/executions/{execution_id}").json()
    assert result["status"] == "completed"
    assert result["invoice_id"]
    assert result["finished_at"]
    assert "content" not in result
    assert len(http.get("/api/v1/executions").json()) == 1


def test_invalid_extraction_goes_to_review(client):
    http, factory = client
    execution_id = submit(http, pdf("sem campos")).json()["id"]
    with factory() as db:
        process_execution(db, execution_id)
        assert db.scalar(select(Invoice)) is None
    result = http.get(f"/api/v1/executions/{execution_id}").json()
    assert result["status"] == "needs_review"
    assert result["error"]


def test_duplicate_invoice_is_terminal(client):
    http, factory = client
    http.post("/api/v1/invoices", json=payload())
    execution_id = submit(http, pdf()).json()["id"]
    with factory() as db:
        process_execution(db, execution_id)
        assert db.get(Execution, execution_id).status == "duplicate"
        assert db.scalar(select(Document)) is None


def test_unexpected_failure_rolls_back_claim(client, monkeypatch):
    import pytest

    import app.executions as service

    http, factory = client
    execution_id = submit(http, pdf()).json()["id"]
    with monkeypatch.context() as patch:
        patch.setattr(service, "extract_invoice", lambda content: (_ for _ in ()).throw(RuntimeError("temporary")))
        with factory() as db, pytest.raises(RuntimeError):
            process_execution(db, execution_id)
    assert http.get(f"/api/v1/executions/{execution_id}").json()["status"] == "queued"
    with factory() as db:
        process_execution(db, execution_id)
    assert http.get(f"/api/v1/executions/{execution_id}").json()["status"] == "completed"


def test_not_found(client):
    assert client[0].get("/api/v1/executions/missing").status_code == 404


def test_dispatch_failure_preserves_pending_execution(client, monkeypatch):
    import app.worker as worker

    http, factory = client
    execution_id = submit(http, pdf()).json()["id"]
    monkeypatch.setattr(worker, "SessionLocal", factory)

    def unavailable(*args):
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr(worker.process_document, "delay", unavailable)
    assert worker.dispatch_pending.run() == 0
    assert http.get(f"/api/v1/executions/{execution_id}").json()["status"] == "queued"
    published = []
    monkeypatch.setattr(worker.process_document, "delay", published.append)
    assert worker.dispatch_pending.run() == 0
    from datetime import datetime, timedelta

    with factory() as db:
        execution = db.get(Execution, execution_id)
        assert execution.dispatch_attempts == 1
        execution.next_dispatch_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert worker.dispatch_pending.run() == 1
    assert published == [execution_id]


def test_reservation_backoff_and_exhaustion(client):
    from datetime import datetime, timedelta

    from app.executions import expire_exhausted, reserve_dispatch

    http, factory = client
    execution_id = submit(http, pdf()).json()["id"]
    now = datetime.now(UTC) + timedelta(seconds=1)
    with factory() as db:
        for attempt in range(5):
            assert reserve_dispatch(db, execution_id, now)
            assert not reserve_dispatch(db, execution_id, now)
            now += timedelta(seconds=60 * 2**attempt + 1)
        expire_exhausted(db, now)
        assert db.get(Execution, execution_id).status == "failed"
        assert not reserve_dispatch(db, execution_id, now)
