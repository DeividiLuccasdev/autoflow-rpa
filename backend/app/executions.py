"""Fila durável no banco; Redis recebe somente identificadores."""
import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .documents import DocumentError, extract_invoice
from .models import AuditEvent, Document, Execution, Invoice
from .integrity import is_duplicate

MAX_ATTEMPTS = 5
LEASE_SECONDS = 60

def enqueue(db, content, owner_id="legacy"):
    digest = hashlib.sha256(content).hexdigest()
    execution = Execution(sha256=digest, content=content, owner_id=owner_id)
    db.add(execution)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if not is_duplicate(exc, "executions", ["owner_id", "sha256"], "executions_sha256_key"):
            raise
        return db.scalar(select(Execution).where(Execution.sha256 == digest, Execution.owner_id == owner_id))
    db.refresh(execution)
    return execution

def process_execution(db, execution_id):
    # Claim e efeitos na mesma transação: queda do worker desfaz ambos.
    # UPDATE condicional serializa entregas concorrentes também no PostgreSQL.
    claimed = db.execute(update(Execution).where(Execution.id == execution_id, Execution.status == "queued").values(status="processing", error=None))
    if claimed.rowcount != 1:
        db.rollback()
        return
    execution = db.get(Execution, execution_id)
    try:
        payload = extract_invoice(execution.content)
    except DocumentError as exc:
        execution.status = "needs_review"
        execution.error = str(exc)
    else:
        try:
            with db.begin_nested():
                invoice = Invoice(**payload.model_dump(), owner_id=execution.owner_id)
                db.add(invoice)
                db.flush()
                db.add(Document(invoice_id=invoice.id, owner_id=execution.owner_id, sha256=execution.sha256, content=execution.content))
                db.add_all([AuditEvent(invoice_id=invoice.id, event="invoice.validated", actor="worker"), AuditEvent(invoice_id=invoice.id, event="document.extracted", actor="worker")])
                db.flush()
            execution.invoice_id = invoice.id
            execution.status = "completed"
        except IntegrityError as exc:
            if not (is_duplicate(exc, "invoices", ["owner_id", "issuer_cnpj", "number", "series"], "uq_invoice_identity") or
                    is_duplicate(exc, "documents", ["owner_id", "sha256"], "documents_sha256_key")):
                raise
            execution.status = "duplicate"
            execution.error = "Nota ou documento já cadastrado"
    execution.finished_at = datetime.now(timezone.utc)
    db.commit()

def reserve_dispatch(db, execution_id, now):
    """Reserva a janela de publicação antes de acessar o Redis."""
    attempts = db.scalar(select(Execution.dispatch_attempts).where(Execution.id == execution_id))
    if attempts is None:
        return False
    result = db.execute(update(Execution).where(
        Execution.id == execution_id, Execution.status == "queued",
        Execution.next_dispatch_at <= now, Execution.dispatch_attempts == attempts, Execution.dispatch_attempts < MAX_ATTEMPTS,
    ).values(dispatch_attempts=Execution.dispatch_attempts + 1,
             next_dispatch_at=now + timedelta(seconds=LEASE_SECONDS * 2 ** attempts)))
    db.commit()
    return result.rowcount == 1

def expire_exhausted(db, now):
    db.execute(update(Execution).where(
        Execution.status == "queued", Execution.dispatch_attempts >= MAX_ATTEMPTS,
        Execution.next_dispatch_at <= now,
    ).values(status="failed", error="Limite de tentativas atingido; requer intervenção", finished_at=now))
    db.commit()

def record_failure(db, execution_id):
    # Não inclui stack trace, credenciais ou conteúdo do PDF na resposta pública.
    db.execute(update(Execution).where(Execution.id == execution_id, Execution.status == "queued")
               .values(error="Falha temporária de processamento; nova tentativa agendada"))
    db.commit()
