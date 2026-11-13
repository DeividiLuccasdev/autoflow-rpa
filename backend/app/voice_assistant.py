"""Assistente demonstrativo por R.E.: autenticação, escopo e documentos fictícios.

Contas públicas de demonstração, isoladas das contas privadas e dos documentos reais.
"""
import hashlib
import os
import re
import secrets
import unicodedata
from collections import OrderedDict
from datetime import datetime, timezone
from threading import RLock
from time import monotonic

import pymupdf
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from .accounts import password_hash, verify_password
from .demo import ASSETS

router = APIRouter(include_in_schema=False)
sessions = OrderedDict()
lock = RLock()
TTL, MAX_SESSIONS = 1200, 128
COOKIE = "autoflow_voice_demo"
DEMO_PASSWORD = "AutoflowDemo2026!"
DEMO_HASH = password_hash(DEMO_PASSWORD)
PROFILES = {
    "05": {"re":"05", "name":"Ana · funcionária fictícia", "role":"Funcionário", "units":["Araraquara","São Carlos"], "full_identifier":True, "download":True, "full_record":False},
    "10": {"re":"10", "name":"Bruno · diretor fictício", "role":"Diretoria", "units":["Araraquara","São Carlos"], "full_identifier":True, "download":True, "full_record":True},
}
DOCUMENTS = [
    {"id":"nf-101", "number":"101", "unit":"Araraquara", "date":"2026-11-10", "tax_type":"CPF", "tax_id":"00000000001", "recipient":"Pessoa Exemplo A", "amount":"123.45", "description":"Serviço demonstrativo A", "status":"Validada"},
    {"id":"nf-102", "number":"102", "unit":"São Carlos", "date":"2026-11-11", "tax_type":"CPF", "tax_id":"00000000001", "recipient":"Pessoa Exemplo A", "amount":"200.00", "description":"Serviço demonstrativo B", "status":"Em revisão"},
    {"id":"nf-103", "number":"103", "unit":"Araraquara", "date":"2026-11-12", "tax_type":"CNPJ", "tax_id":"12345678000195", "recipient":"Empresa Exemplo", "amount":"300.00", "description":"Serviço demonstrativo C", "status":"Validada"},
    {"id":"nf-104", "number":"104", "unit":"São Carlos", "date":"2026-11-13", "tax_type":"CNPJ", "tax_id":"12345678000195", "recipient":"Empresa Exemplo", "amount":"87.65", "description":"Serviço demonstrativo D", "status":"Validada"},
]

# Dados adicionais exclusivamente fictícios da ficha de cobrança.
DEBT_RECORDS = {
    "nf-101": {"debtor_name":"Aurora Horizonte Serviços Demonstrativos Ltda.", "outstanding_amount":"123.45", "address":"Rua Fictícia das Acácias, 101 · Bairro Exemplo · Araraquara/SP", "phone":"(00) 00000-0101", "total_debt":"740.70", "remaining_installments":6},
    "nf-102": {"debtor_name":"Aurora Horizonte Serviços Demonstrativos Ltda.", "outstanding_amount":"200.00", "address":"Avenida Fictícia do Sol, 202 · Bairro Exemplo · São Carlos/SP", "phone":"(00) 00000-0102", "total_debt":"800.00", "remaining_installments":4},
    "nf-103": {"debtor_name":"Órbita Azul Comércio e Soluções Fictícias Ltda.", "outstanding_amount":"300.00", "address":"Rua Fictícia das Estrelas, 303 · Bairro Exemplo · Araraquara/SP", "phone":"(00) 00000-0103", "total_debt":"1500.00", "remaining_installments":5},
    "nf-104": {"debtor_name":"Órbita Azul Comércio e Soluções Fictícias Ltda.", "outstanding_amount":"87.65", "address":"Alameda Fictícia da Lua, 404 · Bairro Exemplo · São Carlos/SP", "phone":"(00) 00000-0104", "total_debt":"262.95", "remaining_installments":3},
}


def clean_sessions():
    for token in list(sessions):
        if monotonic() - sessions[token]["started"] >= TTL:
            del sessions[token]


def identity(request: Request):
    token = request.cookies.get(COOKIE, "")
    with lock:
        clean_sessions()
        session = sessions.get(hashlib.sha256(token.encode()).hexdigest())
        if session is None:
            raise HTTPException(401, "Entre com o R.E. e a senha de demonstração")
        if request.method == "POST" and not secrets.compare_digest(request.headers.get("X-Voice-CSRF", "").encode(), session["csrf"].encode()):
            raise HTTPException(403, "Sessão inválida; entre novamente")
        return session


def record(session, action, detail):
    session["events"].append({"action":action,"detail":detail,"re":session["profile"]["re"],"time":datetime.now(timezone.utc).isoformat()})
    session["events"] = session["events"][-100:]


def serialize(document, profile):
    result = dict(document)
    debt = DEBT_RECORDS[document["id"]]
    result.update({key:debt[key] for key in ("debtor_name","outstanding_amount")})
    if profile["full_record"]:
        result.update({key:debt[key] for key in ("address","phone","total_debt","remaining_installments")})
    if not profile["full_identifier"]:
        result["tax_id"] = "*" * (len(document["tax_id"]) - 2) + document["tax_id"][-2:]
    result["can_download"] = profile["download"]
    result["items"] = [{"description":document["description"],"quantity":1,"unit_price":document["amount"],"total":document["amount"]}]
    result["scope"] = "Documento fictício de demonstração, sem valor fiscal"
    return result


def authorized_document(session, document_id):
    document = next((d for d in DOCUMENTS if d["id"] == document_id and d["unit"] in session["profile"]["units"]), None)
    if document is None:
        record(session,"document.denied","Documento não disponível no escopo do perfil")
        raise HTTPException(404, "Documento não encontrado no seu escopo de acesso")
    return document


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    re: str = Field(pattern=r"^[0-9]{2}$")
    password: str = Field(min_length=1,max_length=128,repr=False)


class Query(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1,max_length=240)


@router.get("/assistente")
def page():
    return FileResponse(ASSETS / "assistant.html")


@router.post("/assistant/login")
def login(body: Login, request: Request, response: Response):
    valid = verify_password(body.password, DEMO_HASH)
    profile = PROFILES.get(body.re)
    if not valid or profile is None:
        raise HTTPException(401,"R.E. ou senha de demonstração inválidos")
    with lock:
        clean_sessions()
        old = hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest()
        sessions.pop(old,None)
        if len(sessions) >= MAX_SESSIONS:
            raise HTTPException(429,"Demonstração ocupada; tente novamente em alguns minutos")
        token = secrets.token_urlsafe(32)
        session = {"profile":profile,"csrf":secrets.token_hex(32),"started":monotonic(),"events":[]}
        sessions[hashlib.sha256(token.encode()).hexdigest()] = session
        record(session,"login","Entrada na simulação por R.E.")
        response.set_cookie(COOKIE,token,max_age=TTL,httponly=True,secure=request.url.scheme=="https" or os.getenv("RENDER")=="true",samesite="strict",path="/")
        return {"profile":profile,"csrf_token":session["csrf"],"demo":True}


@router.get("/assistant/me")
def me(session=Depends(identity)):
    return {"profile":session["profile"],"csrf_token":session["csrf"],"demo":True}


@router.post("/assistant/logout",status_code=204)
def logout(request: Request,response: Response,session=Depends(identity)):
    with lock:
        sessions.pop(hashlib.sha256(request.cookies.get(COOKIE,"").encode()).hexdigest(),None)
        response.delete_cookie(COOKIE,path="/",httponly=True,samesite="strict")


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFD",text.lower()) if unicodedata.category(c)!="Mn")


def parse_query(text):
    text = normalize(text)
    words = {"zero":"0","um":"1","uma":"1","dois":"2","duas":"2","tres":"3","quatro":"4","cinco":"5","seis":"6","sete":"7","oito":"8","nove":"9"}
    for word,digit in words.items():
        text = re.sub(rf"\b{word}\b",digit,text)
    tax = "CNPJ" if re.search(r"\bc\s*n\s*p\s*j\b",text) else "CPF" if re.search(r"\bc\s*p\s*f\b",text) else None
    digits = "".join(re.findall(r"\d",text))
    if tax:
        if len(digits) != (14 if tax=="CNPJ" else 11):
            raise HTTPException(422,f"Informe {14 if tax=='CNPJ' else 11} dígitos para {tax}; confira a transcrição")
        return tax,digits
    if re.search(r"\bnota\b",text) and digits and len(digits)<=10:
        return "number",str(int(digits))
    if not digits and re.search(r"\b(listar|minhas|todas)\b",text):
        return "all",None
    raise HTTPException(422,"Diga 'nota 101', 'notas do CPF' seguido de 11 dígitos, ou 'listar minhas notas'")


@router.post("/assistant/query")
def query(body: Query,session=Depends(identity)):
    kind,value = parse_query(body.text)
    with lock:
        visible = [d for d in DOCUMENTS if d["unit"] in session["profile"]["units"]]
        matches = [d for d in visible if kind=="all" or (d["number"]==value if kind=="number" else d["tax_type"]==kind and d["tax_id"]==value)]
        matches.sort(key=lambda d:(d["date"],d["number"]),reverse=True)
        if "ultima" in normalize(body.text):
            matches = matches[:1]
        record(session,"query",f"Busca por {kind}: {len(matches)} documento(s) no escopo autorizado")
        return {"documents":[serialize(d,session["profile"]) for d in matches],"count":len(matches),"message":f"{len(matches)} nota(s) encontrada(s) no seu escopo de acesso"}


@router.get("/assistant/documents/{document_id}")
def document(document_id: str,session=Depends(identity)):
    with lock:
        doc = authorized_document(session,document_id)
        record(session,"document.open",f'Nota {doc["number"]}')
        return serialize(doc,session["profile"])


@router.get("/assistant/documents/{document_id}/pdf")
def pdf(document_id: str,session=Depends(identity)):
    with lock:
        doc = authorized_document(session,document_id)
        if not session["profile"]["download"]:
            record(session,"download.denied","Perfil sem permissão para baixar PDF")
            raise HTTPException(403,"Seu perfil pode consultar, mas não baixar o PDF")
        with pymupdf.open() as output:
            page = output.new_page()
            lines = ["AUTOFLOW - NOTA DEMONSTRATIVA", "DOCUMENTO FICTICIO - SEM VALOR FISCAL",f'Nota: {doc["number"]}',f'Data: {doc["date"]}',f'Unidade: {doc["unit"]}',f'Destinatario: {doc["recipient"]}',f'{doc["tax_type"]}: {doc["tax_id"]}',f'Descricao: {doc["description"]}',f'Quantidade: 1 / Valor unitario: R$ {doc["amount"]}',f'Total: R$ {doc["amount"]}',f'Status: {doc["status"]}']
            fields = serialize(doc, session["profile"])
            lines += [f'Razao social ficticia: {fields["debtor_name"]}',f'Valor devedor da nota: R$ {fields["outstanding_amount"]}']
            if session["profile"]["full_record"]:
                lines += [f'Endereco ficticio: {fields["address"]}',f'Telefone ficticio: {fields["phone"]}',f'Divida total: R$ {fields["total_debt"]}',f'Parcelas restantes: {fields["remaining_installments"]}']
            page.insert_textbox(pymupdf.Rect(45,50,550,790),"\n\n".join(lines),fontsize=10)
            content = output.tobytes()
        record(session,"document.download",f'Nota {doc["number"]}')
        return Response(content,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="autoflow-nota-demo-{doc["number"]}.pdf"'})


@router.get("/assistant/history")
def history(session=Depends(identity)):
    with lock:
        return {"events":list(reversed(session["events"])),"scope":"Eventos da sessão atual de demonstração"}
