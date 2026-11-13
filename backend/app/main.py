"""Aplicação FastAPI: middlewares, rotas e arquivos estáticos."""

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .api import accounts, executions, invoices
from .config import STATIC_DIR
from .db import get_db
from .demo import assistant, automation, batches, collection_email, pages
from .http_security import HttpSecurityMiddleware
from .limits import BodyLimitMiddleware
from .models import Invoice

app = FastAPI(
    title="AutoFlow RPA",
    version="0.1.0",
    description="Automação financeira com dados fictícios: cadastro, extração, validação e auditoria de notas.",
)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(HttpSecurityMiddleware)


@app.get("/health", tags=["Saúde"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["Saúde"])
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db.execute(select(Invoice.id).limit(1))
    except Exception:
        raise HTTPException(503, "Banco indisponível ou migração pendente") from None
    return {"status": "ready"}


for module in (invoices, executions, accounts, pages, automation, batches, assistant, collection_email):
    app.include_router(module.router)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Rotas com senha não devolvem o valor recebido ("input") nos erros de validação.
    if request.url.path.startswith(("/auth/", "/assistant/")):
        return JSONResponse(
            {"detail": [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]}, status_code=422
        )
    return await request_validation_exception_handler(request, exc)
