"""Orquestração demonstrativa com adaptadores de ERP e estado temporário limitado.

Sem acesso a ERPs reais. Lock é por processo; deploy demo usa um worker HTTP.
"""
from collections import OrderedDict
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock
from time import monotonic
from uuid import UUID, uuid4
from fastapi import APIRouter, Header, HTTPException
from .demo import SAMPLE
from .documents import extract_invoice

router = APIRouter(prefix="/demo/automation", include_in_schema=False)
lock = RLock()
sessions = OrderedDict()
TTL = 900
MAX_SESSIONS = 128
MAX_RUNS = 5
STEPS = ["Extrair documento", "Consultar ERP de origem", "Conferir valores", "Registrar no ERP de destino", "Confirmar o lançamento", "Concluir auditoria"]

def context(session_id):
    now = monotonic()
    for key in list(sessions):
        if now - sessions[key]["created"] > TTL:
            del sessions[key]
    key = str(session_id)
    if key not in sessions:
        while len(sessions) >= MAX_SESSIONS:
            sessions.popitem(last=False)
        sessions[key] = {"created": now, "runs": {}, "ledger": {}}
    return sessions[key]

def snapshot(state, run):
    ledger = state["ledger"].get("12345678000195:42:1")
    return {"id": run["id"], "status": run["status"], "step": run["step"],
            "steps": STEPS, "events": list(run["events"]),
            "source": {"name": "NovaTech ERP · origem", "order": "CP-2026-0042", "amount": "123.45", "status": "Aprovado para lançamento"},
            "destination": {"name": "Orbit Finance · destino", "entries": 1 if ledger else 0, "protocol": ledger["protocol"] if ledger else None, "amount": ledger["amount"] if ledger else None},
            "invoice": run.get("invoice"), "temporary": True, "expires_in_seconds": max(0, int(TTL - (monotonic() - state["created"])))}

@router.post("/runs", status_code=201)
def create_run(x_demo_session: UUID = Header(...)):
    with lock:
        state = context(x_demo_session)
        if len(state["runs"]) >= MAX_RUNS:
            raise HTTPException(429, "Limite de cinco demonstrações nesta sessão temporária")
        run = {"id": str(uuid4()), "step": 0, "status": "running", "events": []}
        state["runs"][run["id"]] = run
        return snapshot(state, run)

@router.post("/runs/{run_id}/advance")
def advance(run_id: UUID, expected_step: int, x_demo_session: UUID = Header(...)):
    with lock:
        state = context(x_demo_session)
        run = state["runs"].get(str(run_id))
        if run is None:
            raise HTTPException(404, "Execução expirada ou não encontrada nesta sessão")
        # Requisição repetida não avança duas etapas; o cliente informa a versão.
        if run["status"] != "running" or run["step"] != expected_step:
            return snapshot(state, run)
        step = run["step"]
        identity = "12345678000195:42:1"
        if step == 0:
            run["invoice"] = extract_invoice(SAMPLE.read_bytes()).model_dump(mode="json")
            message = "PDF fictício lido: nota 42, série 1 e CNPJ válido."
        elif step == 1:
            run["source_amount"] = Decimal("123.45")
            message = "Conta a pagar CP-2026-0042 encontrada no adaptador de origem."
        elif step == 2:
            if Decimal(run["invoice"]["amount"]) != run["source_amount"]:
                run["status"] = "needs_review"
                message = "Divergência: lançamento bloqueado."
            else:
                message = "R$ 123,45 na nota e na origem: conferência aprovada."
        elif step == 3:
            if identity in state["ledger"]:
                run["status"] = "duplicate"
                message = "Nota já registrada nesta sessão: novo lançamento bloqueado."
            else:
                state["ledger"][identity] = {"protocol": "DEMO-" + uuid4().hex[:8].upper(), "amount": run["invoice"]["amount"]}
                message = "Lançamento criado no adaptador de destino, em memória."
        elif step == 4:
            entry = state["ledger"].get(identity)
            if entry is None or entry["amount"] != run["invoice"]["amount"]:
                run["status"] = "needs_review"
                message = "Confirmação falhou: revisão necessária."
            else:
                message = "Destino consultado novamente: valor e protocolo confirmados."
        else:
            run["status"] = "completed"
            message = "Fluxo finalizado com eventos e protocolo de demonstração."
        run["events"].append({"step": step, "title": STEPS[step], "message": message,
                              "time": datetime.now(timezone.utc).isoformat()})
        run["step"] += 1
        return snapshot(state, run)
