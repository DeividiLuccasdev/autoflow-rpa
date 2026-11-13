"""Demonstração pública isolada: somente o PDF sintético distribuído pelo app."""

import hashlib

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import STATIC_DIR
from ..documents import extract_invoice

router = APIRouter()
ASSETS = STATIC_DIR
SAMPLE = ASSETS / "nota-ficticia.pdf"


@router.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(ASSETS / "index.html")


@router.get("/workspace", include_in_schema=False)
def workspace():
    return FileResponse(ASSETS / "workspace.html")


@router.get("/demo/sample", include_in_schema=False)
def sample():
    return FileResponse(SAMPLE, media_type="application/pdf", filename="autoflow-nota-ficticia.pdf")


@router.post("/demo/analyze", include_in_schema=False)
def analyze(file: UploadFile = File(...)):
    try:
        content = file.file.read(65537)
        if len(content) > 65536:
            raise HTTPException(413, "Na demonstração, utilize somente o PDF de exemplo")
        if hashlib.sha256(content).digest() != hashlib.sha256(SAMPLE.read_bytes()).digest():
            raise HTTPException(422, "Este ambiente aceita somente o PDF fictício disponível em Baixar exemplo")
        invoice = extract_invoice(content)
        return {
            "invoice": invoice.model_dump(mode="json"),
            "mode": "demo",
            "persisted": False,
            "checks": ["Documento de demonstração reconhecido", "CNPJ validado", "Campos e valor validados"],
        }
    finally:
        file.file.close()
