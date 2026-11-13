"""Lotes reais por HTTP: conciliação, exceções, reenvio e exportação."""

import csv
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from app.demo.batches import FIXTURES


def headers():
    return {"X-Demo-Session": str(uuid4())}


def example(http, auth, request_id=None):
    response = http.post("/demo/batches/example", params={"request_id": str(request_id or uuid4())}, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def finish(http, auth, batch):
    while batch["status"] == "processing":
        result = http.post(
            f"/demo/batches/{batch['id']}/advance", params={"expected_version": batch["version"]}, headers=auth
        )
        assert result.status_code == 200, result.text
        batch = result.json()
    return batch


def decide(http, auth, batch, item, **changes):
    payload = {
        "action": "approve",
        "reason": "Documento conferido; origem ajustada na demonstração.",
        "corrected_source_amount": "200.00",
        **changes,
    }
    return http.post(f"/demo/batches/{batch['id']}/items/{item['id']}/review", headers=auth, json=payload)


def upload(http, auth, names=None, statement=None, request_id=None):
    names = names or ["nota-101.pdf", "nota-104.pdf"]
    files = [("files", (name, (FIXTURES / name).read_bytes(), "application/pdf")) for name in names]
    files.append(
        (
            "statement",
            (
                "extrato.csv",
                statement if statement is not None else (FIXTURES / "extrato.csv").read_bytes(),
                "text/csv",
            ),
        )
    )
    return http.post("/demo/batches", files=files, data={"request_id": str(request_id or uuid4())}, headers=auth)


def test_complete_batch_and_report_are_calculated(client):
    http, _ = client
    auth = headers()
    batch = finish(http, auth, example(http, auth))
    assert batch["status"] == "needs_review"
    assert batch["version"] == batch["total"] == 5
    assert batch["metrics"] == {
        "queued": 0,
        "registered": 2,
        "needs_review": 2,
        "duplicate": 1,
        "invalid": 0,
        "rejected": 0,
        "registered_amount": "211.10",
    }
    assert [row["identity"].split(":")[1] for row in batch["unmatched_statement"]] == ["999"]
    first, mismatch, duplicate, missing, last = batch["items"]
    assert first["protocol"] == duplicate["protocol"]
    assert mismatch["source_amount"] == "210.00" and mismatch["protocol"] is None
    assert missing["reason"] == "missing_source" and last["status"] == "registered"
    assert all(item["events"] for item in batch["items"])
    response = http.get(f"/demo/batches/{batch['id']}/report", headers=auth)
    assert (
        response.status_code == 200 and response.json() == http.get(f"/demo/batches/{batch['id']}", headers=auth).json()
    )
    assert "sample" not in response.text and "attachment" in response.headers["content-disposition"]
    csv_response = http.get(f"/demo/batches/{batch['id']}/report?format=csv", headers=auth)
    rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    assert len(rows) == 6
    assert rows[-1]["resultado"] == "unmatched_statement" and rows[-1]["valor_extrato_original"] == "50.00"
    assert rows[0]["valor_documento"] == "123.45"
    assert rows[2]["resultado"] == "duplicate"


def test_mismatch_approval_and_missing_rejection_are_audited(client):
    http, _ = client
    auth = headers()
    batch = finish(http, auth, example(http, auth))
    mismatch, missing = batch["items"][1], batch["items"][3]
    assert decide(http, auth, batch, missing).status_code == 409
    approved = decide(http, auth, batch, mismatch)
    assert approved.status_code == 200
    batch = approved.json()
    assert batch["metrics"]["registered_amount"] == "411.10"
    corrected = batch["items"][1]
    assert corrected["source_amount"] == "210.00" and corrected["corrected_source_amount"] == "200.00"
    assert corrected["status"] == "registered" and len(corrected["events"]) == 5
    assert decide(http, auth, batch, mismatch).status_code == 409
    rejected = decide(http, auth, batch, missing, action="reject", corrected_source_amount=None)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "completed"
    assert rejected.json()["metrics"]["rejected"] == 1
    assert rejected.json()["metrics"]["registered_amount"] == "411.10"


def test_replayed_creation_and_step_do_not_repeat_effects(client):
    http, _ = client
    auth = headers()
    request_id = uuid4()
    batch = example(http, auth, request_id)
    assert example(http, auth, request_id)["id"] == batch["id"]
    path = f"/demo/batches/{batch['id']}/advance?expected_version=0"
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: http.post(path, headers=auth), range(2)))
    assert all(r.status_code == 200 and r.json()["version"] == 1 for r in responses)
    assert responses[0].json()["items"][0]["protocol"] == responses[1].json()["items"][0]["protocol"]
    batch = finish(http, auth, responses[0].json())
    assert http.post(path, headers=auth).json()["metrics"] == batch["metrics"]


def test_manual_upload_matches_and_invalid_file_is_isolated(client):
    http, _ = client
    auth = headers()
    files = [
        ("files", ("nota.pdf", (FIXTURES / "nota-101.pdf").read_bytes(), "application/pdf")),
        ("files", ("invalido.pdf", b"%PDF-untrusted", "application/pdf")),
        ("statement", ("extrato.csv", (FIXTURES / "extrato.csv").read_bytes(), "text/csv")),
    ]
    response = http.post("/demo/batches", headers=auth, files=files, data={"request_id": str(uuid4())})
    assert response.status_code == 201
    batch = finish(http, auth, response.json())
    assert batch["metrics"]["registered"] == 1 and batch["metrics"]["invalid"] == 1
    assert batch["items"][1]["status"] == "invalid"
    assert batch["metrics"]["registered_amount"] == "123.45"


@pytest.mark.parametrize(
    "statement",
    [
        b"bad,header\n",
        b"cnpj,numero,serie,valor\n",
        b"\xff",
        b"cnpj,numero,serie,valor\n12.345.678/0001-95,101,1,123,45\n",
        b"cnpj,numero,serie,valor\n12.345.678/0001-95,101,1,-123.45\n",
        b"cnpj,numero,serie,valor\n12.345.678/0001-95,101,1,=1+2\n",
        b"cnpj,numero,serie,valor\n12.345.678/0001-95,101,1,123.45\n12.345.678/0001-95,00101,01,123.45\n",
    ],
)
def test_bad_csv_rejected_before_batch_creation(client, statement):
    http, _ = client
    auth = headers()
    assert upload(http, auth, statement=statement).status_code == 422
    assert http.get("/demo/batches/summary", headers=auth).json()["batches"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": "curta"},
        {"reason": " " * 20},
        {"corrected_source_amount": "210.00"},
        {"corrected_source_amount": "200.001"},
        {"action": "bypass"},
    ],
)
def test_invalid_decision_preserves_block(client, changes):
    http, _ = client
    auth = headers()
    batch = finish(http, auth, example(http, auth))
    assert decide(http, auth, batch, batch["items"][1], **changes).status_code == 422
    current = http.get(f"/demo/batches/{batch['id']}", headers=auth).json()
    assert current["items"][1]["status"] == "needs_review"
    assert current["metrics"]["registered_amount"] == "211.10"


def test_session_isolation_budget_and_cross_batch_deduplication(client):
    http, _ = client
    a, b = headers(), headers()
    first = finish(http, a, example(http, a))
    assert http.get(f"/demo/batches/{first['id']}", headers=b).status_code == 404
    assert http.get(f"/demo/batches/{first['id']}/report", headers=b).status_code == 404
    assert decide(http, b, first, first["items"][1]).status_code == 404
    second = finish(http, a, example(http, a))
    assert second["metrics"]["duplicate"] == 3 and second["metrics"]["registered_amount"] == "0.00"
    assert second["items"][0]["protocol"] == first["items"][0]["protocol"]
    assert http.post("/demo/batches/example", params={"request_id": str(uuid4())}, headers=a).status_code == 429
    assert len(http.get("/demo/batches/summary", headers=a).json()["batches"]) == 2


def test_creation_key_conflict_and_file_limits(client):
    http, _ = client
    auth = headers()
    request_id = uuid4()
    assert upload(http, auth, request_id=request_id).status_code == 201
    assert upload(http, auth, names=["nota-102.pdf"], request_id=request_id).status_code == 409
    assert upload(http, auth, names=["nota-101.pdf"] * 7).status_code == 422
    assert upload(http, headers(), statement=b"x" * 16385).status_code == 413


def test_csv_formula_injection_is_neutralized(client):
    http, _ = client
    auth = headers()
    files = [
        ("files", ('=HYPERLINK("evil")', (FIXTURES / "nota-101.pdf").read_bytes(), "application/pdf")),
        ("statement", ("extrato.csv", (FIXTURES / "extrato.csv").read_bytes(), "text/csv")),
    ]
    batch = finish(
        http, auth, http.post("/demo/batches", headers=auth, files=files, data={"request_id": str(uuid4())}).json()
    )
    content = http.get(f"/demo/batches/{batch['id']}/report?format=csv", headers=auth).content.decode("utf-8-sig")
    assert list(csv.reader(io.StringIO(content)))[1][0].startswith("'=HYPERLINK")


def test_sample_zip_contains_valid_documents_and_statement(client):
    response = client[0].get("/demo/batches/samples.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist()) == 5
        assert archive.read("nota-104.pdf").startswith(b"%PDF-")
        assert archive.read("extrato.csv").startswith(b"cnpj,numero,serie,valor")


def test_concurrent_review_has_one_winner(client):
    http, _ = client
    auth = headers()
    batch = finish(http, auth, example(http, auth))
    item = batch["items"][1]
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(lambda action: decide(http, auth, batch, item, action=action), ["approve", "reject"])
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
