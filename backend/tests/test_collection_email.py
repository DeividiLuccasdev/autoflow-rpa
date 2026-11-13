import hashlib
from concurrent.futures import ThreadPoolExecutor

import pymupdf
from test_voice_assistant import login


def test_collection_requires_auth_csrf_and_server_fields(client):
    http, _ = client
    assert http.post("/assistant/documents/nf-101/collection", json={}).status_code == 401
    assert http.get("/assistant/collections").status_code == 401
    headers = login(http)
    assert http.post("/assistant/documents/nf-101/collection", json={}).status_code == 403
    assert (
        http.post(
            "/assistant/documents/nf-101/collection", headers=headers, json={"recipient": "real@example.com"}
        ).status_code
        == 422
    )
    assert http.get("/assistant/collections").json()["receipts"] == []
    assert http.post("/assistant/documents/unknown/collection", headers=headers, json={}).status_code == 404


def test_generates_pdf_and_autofills_exact_collection_email(client):
    http, _ = client
    headers = login(http)
    response = http.post("/assistant/documents/nf-101/collection", headers=headers, json={})
    assert response.status_code == 200
    data = response.json()
    assert data["sender"] == "cobranca@autoflow.example"
    assert data["recipient"] == "financeiro@empresa-ficticia.example"
    assert data["subject"] == "Valores pendentes com nossa empresa"
    assert "nota de número 101 já ocorreu" in data["body"]
    assert "2 dias corridos" in data["body"] and "R$ 123,45" in data["body"]
    assert "Aurora Horizonte Serviços Demonstrativos Ltda." in data["body"]
    assert data["simulated"] and not data["replayed"]
    attachment = http.get(f"/assistant/collections/{data['id']}/pdf")
    assert attachment.status_code == 200 and attachment.content.startswith(b"%PDF-")
    assert hashlib.sha256(attachment.content).hexdigest() == data["attachment"]["sha256"]
    assert len(attachment.content) == data["attachment"]["size"]
    assert "no-store" in attachment.headers["cache-control"]
    with pymupdf.open(stream=attachment.content, filetype="pdf") as document:
        text = "".join(p.get_text() for p in document)
    assert "Nota: 101" in text and "123.45" in text
    assert "Endereco ficticio:" not in text and "Telefone ficticio:" not in text
    history = http.get("/assistant/history").json()["events"]
    assert sum(e["action"] == "collection.email.simulated" for e in history) == 1


def test_collection_retries_preserve_protocol_attachment_and_single_audit(client):
    http, _ = client
    headers = login(http)
    url = "/assistant/documents/nf-103/collection"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: http.post(url, headers=headers, json={}), range(2)))
    assert all(r.status_code == 200 for r in results)
    first, second = [r.json() for r in results]
    assert first["id"] == second["id"] and first["attachment"] == second["attachment"]
    assert sorted([first["replayed"], second["replayed"]]) == [False, True]
    assert len(http.get("/assistant/collections").json()["receipts"]) == 1
    assert (
        sum(e["action"] == "collection.email.simulated" for e in http.get("/assistant/history").json()["events"]) == 1
    )


def test_collection_receipts_and_attachment_are_session_scoped(client):
    http, _ = client
    headers = login(http)
    data = http.post("/assistant/documents/nf-101/collection", headers=headers, json={}).json()
    login(http, "10")
    assert http.get("/assistant/collections").json()["receipts"] == []
    assert http.get(f"/assistant/collections/{data['id']}/pdf").status_code == 404
    assert http.get("/assistant/collections/missing/pdf").status_code == 404


def test_director_attachment_preserves_authorized_full_record(client):
    http, _ = client
    headers = login(http, "10")
    data = http.post("/assistant/documents/nf-104/collection", headers=headers, json={}).json()
    attachment = http.get(f"/assistant/collections/{data['id']}/pdf")
    with pymupdf.open(stream=attachment.content, filetype="pdf") as document:
        text = "".join(p.get_text() for p in document)
    assert "Endereco ficticio:" in text and "Parcelas restantes: 3" in text
    assert "Alameda" not in data["body"]
