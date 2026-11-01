from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pymupdf
from sqlalchemy import func, select
from app.models import Invoice, Document, AuditEvent, Execution

TEXT="CNPJ emitente: 12.345.678/0001-95\nNumero: 42\nSerie: 1\nValor total: 123.45"

def pdf(text=TEXT, pages=1, password=False):
    with pymupdf.open() as document:
        for _ in range(pages):
            document.new_page().insert_text((60,70),text)
        return document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner",user_pw="secret") if password else document.tobytes()

def payload(**changes):
    return {"issuer_cnpj":"12.345.678/0001-95","number":"00042","series":"01","amount":"123.45",**changes}

def counts(spec):
    with spec["factory"]() as db:
        return [db.scalar(select(func.count()).select_from(model)) for model in (Invoice,Document,AuditEvent,Execution)]

def upload(http,content,path="/api/v1/invoices/upload",name="nota.pdf",mime="application/pdf"):
    return http.post(path,files={"file":(name,content,mime)})

def simultaneous(*actions):
    barrier=Barrier(len(actions))
    def run(action):
        barrier.wait(timeout=10)
        return action()
    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run,actions))
