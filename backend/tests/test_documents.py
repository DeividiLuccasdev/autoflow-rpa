import pymupdf
import pytest
from sqlalchemy import select
from app.models import AuditEvent, Document
from test_invoices import client

TEXT = "AutoFlow - DOCUMENTO FICTICIO\nCNPJ emitente: 12.345.678/0001-95\nNumero: 42\nSerie: 1\nValor total: 123.45"

def pdf(text=TEXT):
    with pymupdf.open() as document:
        page = document.new_page()
        if text:
            page.insert_text((60, 70), text)
        return document.tobytes()

def upload(http, content, mime="application/pdf"):
    return http.post("/api/v1/invoices/upload", files={"file": ("nota.pdf", content, mime)})

def test_upload_persists_original_and_audit(client):
    http, factory = client
    content = pdf()
    response = upload(http, content)
    assert response.status_code == 201
    assert response.json()["amount"] == "123.45"
    with factory() as session:
        document = session.scalar(select(Document))
        assert document.content == content
        assert document.invoice_id == response.json()["id"]
        assert len(session.scalars(select(AuditEvent)).all()) == 2
    assert upload(http, content).status_code == 409
    with factory() as session:
        assert len(session.scalars(select(Document)).all()) == 1

@pytest.mark.parametrize("content,code", [
    (b"not a PDF", 422), (b"%PDF-broken", 422),
    (pdf(""), 422), (pdf(TEXT.replace("Serie: 1", "")), 422),
    (pdf(TEXT + "\nNumero: 43"), 422),
    (pdf(TEXT.replace("123.45", "123,45")), 422),
    (pdf(TEXT.replace("123.45", "0.00")), 422),
    (b"%PDF-" + b"x" * (5 * 1024 * 1024), 413),
])
def test_invalid_upload_creates_nothing(client, content, code):
    http, factory = client
    assert upload(http, content).status_code == code
    assert http.get("/api/v1/invoices").json() == []
    with factory() as session:
        assert session.scalar(select(Document)) is None
        assert session.scalar(select(AuditEvent)) is None

def test_reject_non_pdf_mime(client):
    assert upload(client[0], pdf(), "text/plain").status_code == 415

def test_existing_json_invoice_blocks_pdf(client):
    from test_invoices import payload
    http, _ = client
    assert http.post("/api/v1/invoices", json=payload()).status_code == 201
    assert upload(http, pdf()).status_code == 409

def test_page_limit_and_password(client):
    with pymupdf.open() as document:
        for _ in range(11):
            document.new_page()
        assert upload(client[0], document.tobytes()).status_code == 422
    with pymupdf.open() as document:
        document.new_page().insert_text((60, 70), TEXT)
        content = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    assert upload(client[0], content).status_code == 422
