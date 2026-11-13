"""ERP fictício separado da API pública. Execute somente em 127.0.0.1."""

import os
import sqlite3
from contextlib import asynccontextmanager
from html import escape

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from app.schemas import InvoiceCreate


def connect():
    return sqlite3.connect(os.getenv("RPA_SIM_DB", "simulator.db"), timeout=10)


@asynccontextmanager
async def lifespan(app):
    with connect() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS invoices (cnpj TEXT, number TEXT, series TEXT, amount TEXT, protocol TEXT, UNIQUE(cnpj,number,series))"
        )
    yield


app = FastAPI(title="Orbit Finance - ERP fictício local", lifespan=lifespan)


def screen(message="", status_code=200):
    with connect() as db:
        rows = db.execute("SELECT cnpj,number,series,amount,protocol FROM invoices ORDER BY rowid DESC").fetchall()
    ledger = "".join(
        f'<tr data-testid="invoice-{escape(cnpj)}-{escape(number)}-{escape(series)}"><td>{escape(cnpj)}</td><td>{escape(number)}</td><td>{escape(series)}</td><td>R$ {escape(amount)}</td><td>{escape(protocol)}</td></tr>'
        for cnpj, number, series, amount, protocol in rows
    )
    return HTMLResponse(
        f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Orbit Finance | ERP fictício</title>
<style>body{{background:#0b1120;color:#dce8fa;font:16px system-ui;padding:40px;max-width:1100px;margin:auto}}h1{{color:#62e1ca}}small,p{{color:#9aacc5}}form{{display:grid;grid-template-columns:1fr 1fr;gap:18px;background:#162337;padding:24px;border-radius:12px}}label{{display:grid;gap:8px}}input{{padding:12px;border:1px solid #36516c;border-radius:6px;background:#0b1728;color:white}}button{{padding:14px;background:#63dfc6;border:0;border-radius:6px;font-weight:700;cursor:pointer}}table{{width:100%;border-collapse:collapse;margin-top:25px}}th,td{{text-align:left;padding:14px;border-bottom:1px solid #30425b;font-size:13px}}[role=status]{{padding:15px;color:#84e5b1}}</style>
<small>SISTEMA FICTÍCIO / AMBIENTE LOCAL</small><h1>Orbit Finance</h1><p>Lançamentos de notas fiscais · automação de navegador</p>
<form action="/invoices" method="post"><label>CNPJ emitente<input name="issuer_cnpj" required maxlength="18"></label><label>Número da nota<input name="number" required maxlength="30"></label><label>Série<input name="series" required maxlength="10"></label><label>Valor total<input name="amount" required></label><button type="submit">Salvar lançamento</button></form>
<div role="status">{escape(message)}</div><h2>Lançamentos confirmados</h2><table><thead><tr><th>CNPJ</th><th>Nota</th><th>Série</th><th>Valor</th><th>Protocolo</th></tr></thead><tbody>{ledger}</tbody></table><p>Apenas dados fictícios. Este ERP não realiza pagamentos.</p></html>""",
        status_code=status_code,
    )


@app.get("/", response_class=HTMLResponse)
def index(saved: bool = False):
    return screen("Lançamento salvo e confirmado." if saved else "")


@app.post("/invoices", response_class=HTMLResponse)
def save(issuer_cnpj: str = Form(...), number: str = Form(...), series: str = Form(...), amount: str = Form(...)):
    from uuid import uuid4

    try:
        invoice = InvoiceCreate(issuer_cnpj=issuer_cnpj, number=number, series=series, amount=amount)
    except ValidationError:
        return screen("Dados inválidos; nenhum lançamento salvo.", 422)
    protocol = "RPA-" + uuid4().hex[:12].upper()
    with connect() as db:
        try:
            db.execute(
                "INSERT INTO invoices VALUES (?,?,?,?,?)",
                (invoice.issuer_cnpj, invoice.number, invoice.series, f"{invoice.amount:.2f}", protocol),
            )
        except sqlite3.IntegrityError:
            return screen("Já cadastrado: duplicidade bloqueada.", 409)
    return RedirectResponse("/?saved=true", status_code=303)
