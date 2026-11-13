from contextlib import asynccontextmanager
import hashlib
import os
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, UploadFile
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import AuditEvent, Document, Execution, Invoice
from .executions import enqueue
from .documents import DocumentError, MAX_BYTES, extract_invoice
from .schemas import AuditRead, ExecutionRead, InvoiceCreate, InvoiceRead
from .security import require_api_key
from .integrity import is_duplicate
from .limits import BodyLimitMiddleware
from .http_security import HttpSecurityMiddleware
from .demo import router as demo_router, ASSETS
from .demo_automation import router as automation_router
from .demo_batches import router as batches_router
from .voice_assistant import router as voice_router
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from .accounts import router as accounts_router

router = APIRouter(dependencies=[Depends(require_api_key)])

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="AutoFlow RPA", version="0.1.0", lifespan=lifespan,
              description="MVP local com dados fictícios. Cadastro e validação de notas; sem lançamentos externos.")
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(HttpSecurityMiddleware)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db.execute(select(Invoice.id).limit(1))
    except Exception:
        raise HTTPException(503, "Banco indisponível ou migração pendente")
    return {"status": "ready"}

@router.post("/api/v1/invoices", response_model=InvoiceRead, status_code=201)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db), identity=Depends(require_api_key)):
    return save_invoice(payload, db, owner_id=identity["owner_id"], actor=identity["actor"])

def save_invoice(payload: InvoiceCreate, db: Session, content: bytes | None = None, owner_id="legacy", actor="local-operator"):
    invoice = Invoice(**payload.model_dump(), owner_id=owner_id)
    db.add(invoice)
    try:
        db.flush()
        db.add(AuditEvent(invoice_id=invoice.id, event="invoice.validated", actor=actor))
        if content is not None:
            db.add(Document(invoice_id=invoice.id, owner_id=owner_id, sha256=hashlib.sha256(content).hexdigest(), content=content))
            db.add(AuditEvent(invoice_id=invoice.id, event="document.extracted", actor=actor))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if not (is_duplicate(exc, "invoices", ["owner_id", "issuer_cnpj", "number", "series"], "uq_invoice_identity") or
                is_duplicate(exc, "documents", ["owner_id", "sha256"], "documents_sha256_key")):
            raise
        raise HTTPException(409, "Nota já cadastrada para este emitente, número e série")
    db.refresh(invoice)
    return invoice

@router.post("/api/v1/invoices/upload", response_model=InvoiceRead, status_code=201)
def upload_invoice(file: UploadFile = File(...), db: Session = Depends(get_db), identity=Depends(require_api_key)):
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(415, "Envie um arquivo application/pdf")
        content = file.file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, "O limite do PDF é 5 MiB")
        try:
            payload = extract_invoice(content)
        except DocumentError as exc:
            raise HTTPException(422, str(exc)) from exc
        return save_invoice(payload, db, content, owner_id=identity["owner_id"], actor=identity["actor"])
    finally:
        file.file.close()

@router.get("/api/v1/invoices", response_model=list[InvoiceRead])
def list_invoices(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db), identity=Depends(require_api_key)):
    return db.scalars(select(Invoice).where(Invoice.owner_id == identity["owner_id"]).order_by(Invoice.created_at.desc(), Invoice.id).offset(offset).limit(limit)).all()

@router.get("/api/v1/invoices/{invoice_id}/events", response_model=list[AuditRead])
def invoice_events(invoice_id: str, db: Session = Depends(get_db), identity=Depends(require_api_key)):
    if db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.owner_id == identity["owner_id"])) is None:
        raise HTTPException(404, "Nota não encontrada")
    return db.scalars(select(AuditEvent).where(AuditEvent.invoice_id == invoice_id).order_by(AuditEvent.created_at, AuditEvent.id)).all()

@router.post("/api/v1/executions", response_model=ExecutionRead, status_code=202)
def submit_execution(file: UploadFile = File(...), db: Session = Depends(get_db), identity=Depends(require_api_key)):
    try:
        if os.getenv("AUTOFLOW_ASYNC_ENABLED", "true").lower() != "true":
            raise HTTPException(503, "Fila desativada nesta demonstração; use /api/v1/invoices/upload")
        if file.content_type != "application/pdf":
            raise HTTPException(415, "Envie um arquivo application/pdf")
        content = file.file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, "O limite do PDF é 5 MiB")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(422, "O arquivo não possui assinatura PDF")
        return enqueue(db, content, owner_id=identity["owner_id"])
    finally:
        file.file.close()

@router.get("/api/v1/executions", response_model=list[ExecutionRead])
def list_executions(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db), identity=Depends(require_api_key)):
    return db.scalars(select(Execution).where(Execution.owner_id == identity["owner_id"]).order_by(Execution.created_at.desc(), Execution.id).offset(offset).limit(limit)).all()

@router.get("/api/v1/executions/{execution_id}", response_model=ExecutionRead)
def get_execution(execution_id: str, db: Session = Depends(get_db), identity=Depends(require_api_key)):
    execution = db.scalar(select(Execution).where(Execution.id == execution_id, Execution.owner_id == identity["owner_id"]))
    if execution is None:
        raise HTTPException(404, "Execução não encontrada")
    return execution

app.include_router(router)
app.include_router(accounts_router)
app.include_router(demo_router)
app.include_router(automation_router)
app.include_router(batches_router)
app.include_router(voice_router)
app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    from fastapi.exception_handlers import request_validation_exception_handler
    from fastapi.responses import JSONResponse
    if request.url.path.startswith(("/auth/", "/assistant/")):
        return JSONResponse({"detail": [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]}, status_code=422)
    return await request_validation_exception_handler(request, exc)
