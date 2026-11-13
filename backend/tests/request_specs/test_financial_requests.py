"""describe Cadastro e upload financeiro: todas as ações passam por HTTP."""

import pytest
from helpers import TEXT, counts, payload, pdf, simultaneous, upload
from sqlalchemy import select, text

from app.models import Document


def test_quando_dados_validos_entao_cadastra_e_audita(spec):
    http = spec["http"]
    response = http.post("/api/v1/invoices", json=payload())
    assert response.status_code == 201
    invoice = response.json()
    assert (invoice["number"], invoice["series"], invoice["amount"]) == ("42", "1", "123.45")
    events = http.get(f"/api/v1/invoices/{invoice['id']}/events").json()
    assert [(e["event"], e["actor"]) for e in events] == [("invoice.validated", "local-operator")]
    assert counts(spec) == [1, 0, 1, 0]


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": "0"},
        {"amount": "-1"},
        {"amount": "1.001"},
        {"amount": "1000000000000.00"},
        {"issuer_cnpj": "11111111111111"},
        {"issuer_cnpj": "12345678000100"},
        {"number": "abc"},
        {"series": "X"},
        {"unexpected": True},
    ],
)
def test_quando_campo_invalido_entao_rejeita_sem_gravar(spec, changes):
    assert spec["http"].post("/api/v1/invoices", json=payload(**changes)).status_code == 422
    assert counts(spec) == [0, 0, 0, 0]


@pytest.mark.parametrize("missing", ["issuer_cnpj", "number", "amount"])
def test_quando_campo_obrigatorio_ausente_entao_rejeita(spec, missing):
    body = payload()
    del body[missing]
    assert spec["http"].post("/api/v1/invoices", json=body).status_code == 422
    assert counts(spec) == [0, 0, 0, 0]


def test_quando_nota_repetida_normalizada_entao_retorna_conflito(spec):
    http = spec["http"]
    assert http.post("/api/v1/invoices", json=payload()).status_code == 201
    assert (
        http.post("/api/v1/invoices", json=payload(issuer_cnpj="12345678000195", number="42", series="1")).status_code
        == 409
    )
    assert counts(spec) == [1, 0, 1, 0]


def test_quando_duas_requisicoes_simultaneas_entao_so_uma_nota(spec):
    http = spec["http"]
    responses = simultaneous(*[lambda: http.post("/api/v1/invoices", json=payload()) for _ in range(2)])
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert counts(spec) == [1, 0, 1, 0]


def test_quando_identidades_distintas_entao_cadastra_ambas(spec):
    for number in ["42", "43"]:
        assert spec["http"].post("/api/v1/invoices", json=payload(number=number)).status_code == 201
    assert counts(spec) == [2, 0, 2, 0]


def test_quando_banco_recusa_auditoria_entao_transacao_desfaz_nota(spec):
    # Falha real de persistência no banco exclusivo do teste, sem mock de regras.
    with spec["engine"].begin() as connection:
        connection.execute(
            text("ALTER TABLE audit_events ADD CONSTRAINT audit_test_failure CHECK (event <> 'invoice.validated')")
        )
    response = spec["http"].post("/api/v1/invoices", json=payload())
    assert response.status_code == 500
    assert counts(spec) == [0, 0, 0, 0]
    assert "INSERT" not in response.text and "password" not in response.text


def test_quando_upload_valido_entao_preserva_documento_e_auditoria(spec):
    content = pdf()
    response = upload(spec["http"], content)
    assert response.status_code == 201
    assert counts(spec) == [1, 1, 2, 0]
    with spec["factory"]() as db:
        assert db.scalar(select(Document)).content == content


@pytest.mark.parametrize(
    "kind,code",
    [
        ("corrupt", 422),
        ("password", 422),
        ("blank", 422),
        ("missing", 422),
        ("repeated", 422),
        ("pages", 422),
        ("oversized", 413),
        ("mime", 415),
    ],
)
def test_quando_documento_invalido_entao_nao_grava(spec, kind, code):
    content = {
        "corrupt": b"%PDF-broken",
        "password": pdf(password=True),
        "blank": pdf(""),
        "missing": pdf(TEXT.replace("Serie: 1", "")),
        "repeated": pdf(TEXT + "\nNumero: 43"),
        "pages": pdf(pages=11),
        "oversized": b"%PDF-" + b"x" * (5 * 1024 * 1024),
        "mime": pdf(),
    }[kind]
    assert upload(spec["http"], content, mime="text/plain" if kind == "mime" else "application/pdf").status_code == code
    assert counts(spec) == [0, 0, 0, 0]


def test_quando_json_antes_do_pdf_entao_nao_duplica(spec):
    assert spec["http"].post("/api/v1/invoices", json=payload()).status_code == 201
    assert upload(spec["http"], pdf()).status_code == 409
    assert counts(spec) == [1, 0, 1, 0]


def test_quando_uploads_simultaneos_entao_so_um_documento(spec):
    content = pdf()
    responses = simultaneous(*[lambda: upload(spec["http"], content) for _ in range(2)])
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert counts(spec) == [1, 1, 2, 0]


def test_quando_nome_tenta_escapar_entao_nao_cria_arquivo(spec):
    destination = spec["tmp"] / "outside.pdf"
    assert upload(spec["http"], pdf(), name=str(destination)).status_code == 201
    assert not destination.exists()
