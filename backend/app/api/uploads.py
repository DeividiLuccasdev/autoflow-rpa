"""Leitura validada de PDFs enviados à API privada."""

from fastapi import HTTPException, UploadFile

from ..documents import MAX_BYTES


def read_pdf_upload(file: UploadFile) -> bytes:
    """Confere tipo, tamanho e assinatura do PDF e devolve o conteúdo; sempre fecha o arquivo."""
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(415, "Envie um arquivo application/pdf")
        content = file.file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, "O limite do PDF é 5 MiB")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(422, "O arquivo não possui assinatura PDF")
        return content
    finally:
        file.file.close()
