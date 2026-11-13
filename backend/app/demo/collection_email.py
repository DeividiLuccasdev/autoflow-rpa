"""Gera PDF e registra cobrança fictícia. Sem SMTP, API de e-mail ou envio externo."""

import hashlib
import secrets
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from .assistant import authorized_document, build_demo_pdf, identity, lock, record, serialize

router = APIRouter(include_in_schema=False)
SENDER = "cobranca@autoflow.example"
RECIPIENT = "financeiro@empresa-ficticia.example"
SUBJECT = "Valores pendentes com nossa empresa"


class CollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.post("/assistant/documents/{document_id}/collection")
def generate_collection(document_id: str, body: CollectionRequest, session=Depends(identity)):
    with lock:
        doc = authorized_document(session, document_id)
        if not session["profile"]["download"]:
            raise HTTPException(403, "Seu perfil não pode gerar a nota anexada")
        outbox = session.setdefault("collection_outbox", {})
        if document_id in outbox:
            return {**outbox[document_id]["receipt"], "replayed": True}
        fields = serialize(doc, session["profile"])
        value = f"{Decimal(fields['outstanding_amount']):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        message = (
            f"Prezados(as), {fields['debtor_name']},\n\n"
            f"Venho, por meio desta, informar que o vencimento da nota de número {doc['number']} já ocorreu. "
            "Concedemos o prazo adicional de 2 dias corridos para o pagamento.\n\n"
            f"Valor pendente da nota: R$ {value}.\n"
            "A nota segue em anexo para conferência.\n\n"
            "Caso o pagamento já tenha sido realizado, favor desconsiderar esta mensagem.\n\n"
            "Atenciosamente,\nEquipe de Cobrança\n\n"
            "DEMONSTRAÇÃO: dados fictícios. Esta mensagem não foi enviada para uma caixa de e-mail real."
        )
        attachment = build_demo_pdf(doc, session["profile"])
        receipt = {
            "id": "COB-" + secrets.token_hex(8).upper(),
            "document_id": document_id,
            "number": doc["number"],
            "sender": SENDER,
            "recipient": RECIPIENT,
            "subject": SUBJECT,
            "body": message,
            "status": "Envio simulado concluído",
            "simulated": True,
            "amount": fields["outstanding_amount"],
            "created_at": datetime.now(UTC).isoformat(),
            "attachment": {
                "filename": f"autoflow-nota-demo-{doc['number']}.pdf",
                "size": len(attachment),
                "sha256": hashlib.sha256(attachment).hexdigest(),
            },
            "replayed": False,
        }
        outbox[document_id] = {"receipt": receipt, "pdf": attachment}
        record(session, "document.generated", f"Nota {doc['number']} gerada para cobrança fictícia")
        record(
            session,
            "collection.email.simulated",
            f"Nota {doc['number']} · protocolo {receipt['id']} · sem envio externo",
        )
        return receipt


@router.get("/assistant/collections")
def collections(session=Depends(identity)):
    with lock:
        receipts = [entry["receipt"] for entry in session.get("collection_outbox", {}).values()]
        return {"receipts": list(reversed(receipts)), "simulated": True}


@router.get("/assistant/collections/{receipt_id}/pdf")
def collection_pdf(receipt_id: str, session=Depends(identity)):
    with lock:
        entry = next(
            (v for v in session.get("collection_outbox", {}).values() if v["receipt"]["id"] == receipt_id), None
        )
        if entry is None:
            raise HTTPException(404, "Cobrança não encontrada nesta sessão")
        authorized_document(session, entry["receipt"]["document_id"])
        if not session["profile"]["download"]:
            raise HTTPException(403, "Seu perfil não pode baixar o PDF")
        record(session, "collection.attachment.download", f"Protocolo {receipt_id}")
        return Response(
            entry["pdf"],
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{entry["receipt"]["attachment"]["filename"]}"'},
        )
