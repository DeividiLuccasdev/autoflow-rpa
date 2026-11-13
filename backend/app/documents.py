"""Parser estrito do formato fictício AutoFlow; não interpreta DANFE real."""

import re
from decimal import Decimal

import pymupdf
from pydantic import ValidationError

from .schemas import InvoiceCreate

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10


class DocumentError(ValueError):
    pass


def extract_invoice(content: bytes) -> InvoiceCreate:
    if not content.startswith(b"%PDF-"):
        raise DocumentError("O arquivo não possui assinatura PDF")
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise DocumentError("PDF protegido por senha não suportado")
            if not 1 <= len(document) <= MAX_PAGES:
                raise DocumentError("Envie um PDF com 1 a 10 páginas")
            text = "\n".join(page.get_text() for page in document)
    except DocumentError:
        raise
    except (RuntimeError, ValueError) as exc:
        raise DocumentError("Não foi possível ler o PDF") from exc
    if not text.strip():
        raise DocumentError("PDF sem texto selecionável; OCR ainda não disponível")
    fields = {}
    labels = {"CNPJ emitente": "issuer_cnpj", "Numero": "number", "Serie": "series", "Valor total": "amount"}
    for label, key in labels.items():
        matches = re.findall(rf"^{re.escape(label)}:[ \t]*(.+?)[ \t]*$", text, re.MULTILINE)
        if len(matches) != 1:
            raise DocumentError(f"Campo ausente ou repetido: {label}")
        fields[key] = matches[0]
    # Sem inferência de separadores monetários: o formato define ponto decimal.
    if not re.fullmatch(r"[0-9]+\.[0-9]{2}", fields["amount"]):
        raise DocumentError("Valor total deve usar ponto e duas casas decimais, por exemplo 123.45")
    fields["amount"] = Decimal(fields["amount"])
    try:
        return InvoiceCreate(**fields)
    except ValidationError as exc:
        raise DocumentError("Dados extraídos inválidos; confira CNPJ, número, série e valor") from exc
