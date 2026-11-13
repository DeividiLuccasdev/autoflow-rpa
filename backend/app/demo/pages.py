"""Demonstração pública isolada: somente o PDF sintético distribuído pelo app."""

import hashlib
import re
from functools import cache

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from ..config import STATIC_DIR
from ..documents import extract_invoice

router = APIRouter()
ASSETS = STATIC_DIR
SAMPLE = ASSETS / "nota-ficticia.pdf"
ASSET_REFERENCE = re.compile(r"/assets/([\w.-]+\.(?:css|js))(?![\w.-])")


@cache
def html_page(name: str) -> str:
    """Lê a página e versiona cada CSS/JS local pelo hash do conteúdo (?v=<sha256[:10]>).

    O navegador baixa de novo um asset somente quando o arquivo muda, sem versões manuais no HTML.
    Os arquivos estáticos não mudam com o processo rodando, então o resultado fica em cache.
    """

    def versioned(match: re.Match) -> str:
        digest = hashlib.sha256((ASSETS / match.group(1)).read_bytes()).hexdigest()[:10]
        return f"{match.group(0)}?v={digest}"

    return ASSET_REFERENCE.sub(versioned, (ASSETS / name).read_text(encoding="utf-8"))


@router.get("/", include_in_schema=False)
def dashboard():
    return HTMLResponse(html_page("index.html"))


@router.get("/workspace", include_in_schema=False)
def workspace():
    return HTMLResponse(html_page("workspace.html"))


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
