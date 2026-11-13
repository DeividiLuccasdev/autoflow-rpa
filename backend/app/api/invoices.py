"""Cadastro, upload e auditoria de notas do usuário autenticado."""

import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..documents import DocumentError, extract_invoice
from ..integrity import is_duplicate
from ..models import AuditEvent, Document, Invoice
from ..schemas import AuditRead, InvoiceCreate, InvoiceRead
from ..security import current_identity
from .uploads import read_pdf_upload

router = APIRouter(prefix="/api/v1/invoices", tags=["Notas"], dependencies=[Depends(current_identity)])


def save_invoice(
    payload: InvoiceCreate, db: Session, content: bytes | None = None, owner_id="legacy", actor="local-operator"
):
    """Grava nota, documento e auditoria na mesma transação; duplicidade conhecida vira 409."""
    invoice = Invoice(**payload.model_dump(), owner_id=owner_id)
    db.add(invoice)
    try:
        db.flush()
        db.add(AuditEvent(invoice_id=invoice.id, event="invoice.validated", actor=actor))
        if content is not None:
            db.add(
                Document(
                    invoice_id=invoice.id,
                    owner_id=owner_id,
                    sha256=hashlib.sha256(content).hexdigest(),
                    content=content,
                )
            )
            db.add(AuditEvent(invoice_id=invoice.id, event="document.extracted", actor=actor))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if not (
            is_duplicate(exc, "invoices", ["owner_id", "issuer_cnpj", "number", "series"], "uq_invoice_identity")
            or is_duplicate(exc, "documents", ["owner_id", "sha256"], "documents_sha256_key")
        ):
            raise
        raise HTTPException(409, "Nota já cadastrada para este emitente, número e série") from None
    db.refresh(invoice)
    return invoice


@router.post("", response_model=InvoiceRead, status_code=201)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db), identity=Depends(current_identity)):
    return save_invoice(payload, db, owner_id=identity["owner_id"], actor=identity["actor"])


@router.post("/upload", response_model=InvoiceRead, status_code=201)
def upload_invoice(file: UploadFile = File(...), db: Session = Depends(get_db), identity=Depends(current_identity)):
    content = read_pdf_upload(file)
    try:
        payload = extract_invoice(content)
    except DocumentError as exc:
        raise HTTPException(422, str(exc)) from exc
    return save_invoice(payload, db, content, owner_id=identity["owner_id"], actor=identity["actor"])


@router.get("", response_model=list[InvoiceRead])
def list_invoices(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    identity=Depends(current_identity),
):
    return db.scalars(
        select(Invoice)
        .where(Invoice.owner_id == identity["owner_id"])
        .order_by(Invoice.created_at.desc(), Invoice.id)
        .offset(offset)
        .limit(limit)
    ).all()


@router.get("/{invoice_id}/events", response_model=list[AuditRead])
def invoice_events(invoice_id: str, db: Session = Depends(get_db), identity=Depends(current_identity)):
    if db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.owner_id == identity["owner_id"])) is None:
        raise HTTPException(404, "Nota não encontrada")
    return db.scalars(
        select(AuditEvent).where(AuditEvent.invoice_id == invoice_id).order_by(AuditEvent.created_at, AuditEvent.id)
    ).all()
