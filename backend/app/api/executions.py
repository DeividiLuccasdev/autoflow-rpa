"""Envio assíncrono de documentos e acompanhamento das execuções."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..executions import enqueue
from ..models import Execution
from ..schemas import ExecutionRead
from ..security import current_identity
from .uploads import read_pdf_upload

router = APIRouter(prefix="/api/v1/executions", tags=["Execuções"], dependencies=[Depends(current_identity)])


@router.post("", response_model=ExecutionRead, status_code=202)
def submit_execution(file: UploadFile = File(...), db: Session = Depends(get_db), identity=Depends(current_identity)):
    if not settings.async_enabled:
        file.file.close()
        raise HTTPException(503, "Fila desativada nesta demonstração; use /api/v1/invoices/upload")
    return enqueue(db, read_pdf_upload(file), owner_id=identity["owner_id"])


@router.get("", response_model=list[ExecutionRead])
def list_executions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    identity=Depends(current_identity),
):
    return db.scalars(
        select(Execution)
        .where(Execution.owner_id == identity["owner_id"])
        .order_by(Execution.created_at.desc(), Execution.id)
        .offset(offset)
        .limit(limit)
    ).all()


@router.get("/{execution_id}", response_model=ExecutionRead)
def get_execution(execution_id: str, db: Session = Depends(get_db), identity=Depends(current_identity)):
    execution = db.scalar(
        select(Execution).where(Execution.id == execution_id, Execution.owner_id == identity["owner_id"])
    )
    if execution is None:
        raise HTTPException(404, "Execução não encontrada")
    return execution
