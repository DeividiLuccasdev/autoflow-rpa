"""Conciliação demonstrativa em lote. PDFs canônicos, origem CSV e destino simulado.

Sem filas externas nesta demonstração: cada avanço processa um documento no backend.
Estado temporário limitado usa o mesmo isolamento por sessão da demonstração existente.
"""

import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError

from ..documents import DocumentError, extract_invoice
from ..schemas import InvoiceCreate
from .automation import TTL, context, lock
from .pages import ASSETS

router = APIRouter(prefix="/demo/batches", include_in_schema=False)
FIXTURES = ASSETS / "batch-samples"
SAMPLES = ["nota-101.pdf", "nota-102.pdf", "nota-103.pdf", "nota-104.pdf"]
MAX_BATCHES = 2
MAX_DOCUMENTS = 6
FIELDS = ["cnpj", "numero", "serie", "valor"]


def key(invoice):
    return f"{invoice['issuer_cnpj']}:{invoice['number']}:{invoice['series']}"


def read_statement(content):
    if len(content) > 16384:
        raise HTTPException(413, "Extrato CSV deve ter até 16 KB")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        if reader.fieldnames != FIELDS:
            raise ValueError("Cabeçalho esperado: cnpj,numero,serie,valor")
        rows = {}
        for index, row in enumerate(reader, start=2):
            if index > 51 or None in row or any(v is None for v in row.values()):
                raise ValueError("Extrato deve ter até 50 linhas válidas, com quatro colunas")
            if not re.fullmatch(r"[0-9]+\.[0-9]{2}", row["valor"]):
                raise ValueError(f"Linha {index}: valor deve usar ponto e duas casas decimais")
            invoice = InvoiceCreate(
                issuer_cnpj=row["cnpj"], number=row["numero"], series=row["serie"], amount=Decimal(row["valor"])
            ).model_dump(mode="json")
            identity = key(invoice)
            if identity in rows:
                raise ValueError("Extrato contém a mesma identidade de nota em mais de uma linha")
            rows[identity] = {"line": index, "amount": invoice["amount"], "identity": identity}
        if not rows:
            raise ValueError("O extrato está vazio")
        return rows
    except (UnicodeError, csv.Error, ValueError, ValidationError) as exc:
        message = (
            str(exc)
            if isinstance(exc, ValueError) and not isinstance(exc, ValidationError)
            else "Extrato inválido; confira CNPJ, número, série e valor"
        )
        raise HTTPException(422, message) from exc


def audit(item, title, message):
    item["events"].append({"title": title, "message": message, "time": datetime.now(UTC).isoformat()})


def report(state, batch):
    items = [{k: v for k, v in item.items() if k != "sample"} for item in batch["items"]]
    identities = {key(item["invoice"]) for item in items if item.get("invoice")}
    counts = {
        status: sum(item["status"] == status for item in items)
        for status in ["queued", "registered", "needs_review", "duplicate", "invalid", "rejected"]
    }
    amount = sum(
        (Decimal(item["invoice"]["amount"]) for item in items if item["status"] == "registered"), Decimal("0.00")
    )
    return {
        "id": batch["id"],
        "version": batch["cursor"],
        "total": len(items),
        "status": "processing" if counts["queued"] else "needs_review" if counts["needs_review"] else "completed",
        "items": items,
        "metrics": {**counts, "registered_amount": str(amount)},
        "unmatched_statement": [row for identity, row in batch["statement"].items() if identity not in identities],
        "elapsed_seconds": round(batch.get("finished", monotonic()) - batch["started"], 3),
        "expires_in_seconds": max(0, int(TTL - (monotonic() - state["created"]))),
        "scope": "Documentos fictícios, extrato de demonstração e destino simulado. Nenhum pagamento ou lançamento em ERP real.",
        "temporary": True,
    }


def find_batch(state, batch_id):
    batch = state.get("batches", {}).get(str(batch_id))
    if batch is None:
        raise HTTPException(404, "Lote não encontrado nesta sessão ou sessão expirada")
    return batch


def make_batch(session_id, request_id, documents, statement_content):
    if not 1 <= len(documents) <= MAX_DOCUMENTS:
        raise HTTPException(422, "Envie de um a seis PDFs por lote")
    statement = read_statement(statement_content)
    fingerprint = hashlib.sha256(
        json.dumps([(name, hashlib.sha256(content).hexdigest()) for name, content in documents]).encode()
        + statement_content
    ).hexdigest()
    allowed = {hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(): name for name in SAMPLES}
    with lock:
        state = context(session_id, create=True)
        batches = state.setdefault("batches", {})
        for batch in batches.values():
            if batch["request_id"] == str(request_id):
                if batch["fingerprint"] != fingerprint:
                    raise HTTPException(409, "Identificador de envio já utilizado com outros arquivos")
                return report(state, batch)
        if len(batches) >= MAX_BATCHES:
            raise HTTPException(429, "Limite de dois lotes nesta sessão temporária")
        items = []
        for name, content in documents:
            sample = allowed.get(hashlib.sha256(content).hexdigest())
            items.append(
                {
                    "id": str(uuid4()),
                    "filename": name.replace("\\", "/").split("/")[-1][:100] or "documento.pdf",
                    "status": "queued",
                    "sample": sample,
                    "events": [],
                    "invoice": None,
                    "source_amount": None,
                    "protocol": None,
                    "reason": None,
                }
            )
        batch = {
            "id": str(uuid4()),
            "request_id": str(request_id),
            "fingerprint": fingerprint,
            "items": items,
            "statement": statement,
            "cursor": 0,
            "seen": {},
            "started": monotonic(),
        }
        batches[batch["id"]] = batch
        return report(state, batch)


@router.get("/samples.zip")
def samples():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in [*SAMPLES, "extrato.csv"]:
            archive.writestr(name, (FIXTURES / name).read_bytes())
    return Response(
        output.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="autoflow-exemplos-conciliacao.zip"'},
    )


@router.post("/example", status_code=201)
def example(request_id: UUID, x_demo_session: UUID = Header(...)):
    names = [SAMPLES[0], SAMPLES[1], SAMPLES[0], SAMPLES[2], SAMPLES[3]]
    return make_batch(
        x_demo_session,
        request_id,
        [(name, (FIXTURES / name).read_bytes()) for name in names],
        (FIXTURES / "extrato.csv").read_bytes(),
    )


@router.post("", status_code=201)
def upload_batch(
    request_id: UUID = Form(...),
    files: list[UploadFile] = File(...),
    statement: UploadFile = File(...),
    x_demo_session: UUID = Header(...),
):
    try:
        if not 1 <= len(files) <= MAX_DOCUMENTS:
            raise HTTPException(422, "Envie de um a seis PDFs por lote")
        documents = []
        for file in files:
            content = file.file.read(65537)
            if len(content) > 65536:
                raise HTTPException(413, "Cada PDF deve ter até 64 KB")
            documents.append((file.filename or "documento.pdf", content))
        return make_batch(x_demo_session, request_id, documents, statement.file.read(16385))
    finally:
        statement.file.close()
        for file in files:
            file.file.close()


@router.get("/summary")
def summary(x_demo_session: UUID = Header(...)):
    with lock:
        state = context(x_demo_session, create=True)
        batches = list(state.get("batches", {}).values())
        return {
            "batches": [report(state, batch) for batch in reversed(batches)],
            "remaining_batches": MAX_BATCHES - len(batches),
        }


@router.get("/{batch_id}")
def get_batch(batch_id: UUID, x_demo_session: UUID = Header(...)):
    with lock:
        state = context(x_demo_session)
        return report(state, find_batch(state, batch_id))


@router.post("/{batch_id}/advance")
def advance(batch_id: UUID, expected_version: int, x_demo_session: UUID = Header(...)):
    with lock:
        state = context(x_demo_session)
        batch = find_batch(state, batch_id)
        if batch["cursor"] != expected_version or batch["cursor"] >= len(batch["items"]):
            return report(state, batch)
        item = batch["items"][batch["cursor"]]
        ledger = state.setdefault("batch_ledger", {})
        audit(item, "Recebido", "Documento recebido no lote da sessão demonstrativa.")
        try:
            if item["sample"] is None:
                raise DocumentError("Este ambiente aceita somente os PDFs fictícios do pacote de exemplos")
            item["invoice"] = extract_invoice((FIXTURES / item["sample"]).read_bytes()).model_dump(mode="json")
            identity = key(item["invoice"])
            audit(
                item,
                "Extraído",
                f"Nota {item['invoice']['number']}, CNPJ, série e valor validados pelo extrator Python.",
            )
            source = batch["statement"].get(identity)
            item["source_amount"] = source["amount"] if source else None
            if identity in batch["seen"] or identity in ledger:
                item["status"] = "duplicate"
                item["reason"] = "Documento já recebido neste lote ou registrado anteriormente nesta sessão."
                item["protocol"] = ledger.get(identity, {}).get("protocol")
                audit(item, "Duplicidade bloqueada", item["reason"])
            else:
                batch["seen"][identity] = item["id"]
                if source is None:
                    item["status"], item["reason"] = "needs_review", "missing_source"
                    audit(
                        item,
                        "Sem correspondência",
                        "Nenhuma linha do extrato corresponde a CNPJ, número e série. Lançamento bloqueado.",
                    )
                elif Decimal(source["amount"]) != Decimal(item["invoice"]["amount"]):
                    item["status"], item["reason"] = "needs_review", "amount_mismatch"
                    audit(
                        item,
                        "Valor divergente",
                        f"Nota: {item['invoice']['amount']}; extrato: {source['amount']}. Lançamento bloqueado.",
                    )
                else:
                    register(ledger, item, identity)
        except DocumentError as exc:
            item["status"], item["reason"] = "invalid", str(exc)
            audit(item, "Documento recusado", str(exc))
        batch["cursor"] += 1
        if batch["cursor"] == len(batch["items"]):
            batch["finished"] = monotonic()
        return report(state, batch)


def register(ledger, item, identity):
    if identity in ledger:
        item["status"], item["protocol"] = "duplicate", ledger[identity]["protocol"]
        audit(item, "Duplicidade bloqueada", "O lançamento já foi confirmado por outra execução da sessão.")
        return
    entry = {"protocol": "LOTE-" + uuid4().hex[:8].upper(), "amount": item["invoice"]["amount"]}
    ledger[identity] = entry
    item["protocol"], item["status"] = ledger[identity]["protocol"], "registered"
    audit(
        item,
        "Registrado e confirmado",
        f"Lançamento de {entry['amount']} confirmado no destino simulado. Protocolo {entry['protocol']}.",
    )


class BatchDecision(BaseModel):
    action: Literal["approve", "reject"]
    reason: str = Field(min_length=10, max_length=300)
    corrected_source_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


@router.post("/{batch_id}/items/{item_id}/review")
def review(batch_id: UUID, item_id: UUID, decision: BatchDecision, x_demo_session: UUID = Header(...)):
    with lock:
        state = context(x_demo_session)
        batch = find_batch(state, batch_id)
        item = next((item for item in batch["items"] if item["id"] == str(item_id)), None)
        if item is None:
            raise HTTPException(404, "Documento não encontrado neste lote")
        if batch["cursor"] < len(batch["items"]) or item["status"] != "needs_review":
            raise HTTPException(409, "Conclua o processamento e selecione um documento pendente")
        if len(decision.reason.strip()) < 10:
            raise HTTPException(422, "Informe uma justificativa com pelo menos dez caracteres")
        if decision.action == "reject":
            item["status"] = "rejected"
            audit(item, "Revisão: rejeitado", decision.reason.strip())
        else:
            if item["reason"] != "amount_mismatch":
                raise HTTPException(
                    409,
                    "Sem correspondência no extrato: aprovação não permitida. Rejeite ou envie um novo lote com extrato corrigido",
                )
            if decision.corrected_source_amount != Decimal(item["invoice"]["amount"]):
                raise HTTPException(422, "Valor corrigido deve coincidir com o documento")
            audit(
                item,
                "Revisão: origem corrigida",
                f"De {item['source_amount']} para {decision.corrected_source_amount}. Justificativa: {decision.reason.strip()}",
            )
            item["corrected_source_amount"] = str(decision.corrected_source_amount)
            register(state.setdefault("batch_ledger", {}), item, key(item["invoice"]))
        return report(state, batch)


def csv_cell(value):
    text = str(value) if value is not None else ""
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


@router.get("/{batch_id}/report")
def download_report(batch_id: UUID, format: Literal["json", "csv"] = "json", x_demo_session: UUID = Header(...)):
    with lock:
        state = context(x_demo_session)
        data = report(state, find_batch(state, batch_id))
    if format == "json":
        content, mime = json.dumps(data, ensure_ascii=False, indent=2), "application/json"
    else:
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(
            [
                "arquivo",
                "nota",
                "valor_documento",
                "valor_extrato_original",
                "valor_corrigido",
                "resultado",
                "protocolo",
                "auditoria",
            ]
        )
        for item in data["items"]:
            values = [
                item["filename"],
                (item["invoice"] or {}).get("number"),
                (item["invoice"] or {}).get("amount"),
                item["source_amount"],
                item.get("corrected_source_amount"),
                item["status"],
                item["protocol"],
                " | ".join(f"{e['title']}: {e['message']}" for e in item["events"]),
            ]
            writer.writerow([csv_cell(value) for value in values])
        for row in data["unmatched_statement"]:
            writer.writerow(
                [
                    f"Extrato linha {row['line']}",
                    row["identity"].split(":")[1],
                    "",
                    row["amount"],
                    "",
                    "unmatched_statement",
                    "",
                    "Nenhum documento corresponde a esta linha do extrato",
                ]
            )
        content, mime = "\ufeff" + output.getvalue(), "text/csv; charset=utf-8"
    return Response(
        content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="autoflow-lote-{batch_id}.{format}"'},
    )
