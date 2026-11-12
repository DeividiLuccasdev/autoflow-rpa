"""Demonstração isolada: adaptadores simulados, sem pagamentos ou ERPs reais.

Estado limitado em memória; requer um único processo HTTP, como no Render.
"""
from collections import OrderedDict
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from .demo import SAMPLE
from .documents import extract_invoice

router = APIRouter(prefix="/demo/automation", include_in_schema=False)
lock = RLock()
sessions = OrderedDict()
TTL = 900
MAX_SESSIONS = 128
MAX_RUNS = 5
STEPS = ["Extrair documento", "Consultar ERP de origem", "Conferir valores", "Registrar no ERP de destino", "Confirmar o lançamento", "Concluir auditoria"]


def context(session_id, create=False):
    now = monotonic()
    for key in list(sessions):
        if now - sessions[key]["created"] > TTL:
            del sessions[key]
    key = str(session_id)
    if key not in sessions:
        if not create:
            raise HTTPException(404, "Sessão expirada ou não encontrada")
        if len(sessions) >= MAX_SESSIONS:
            raise HTTPException(429, "Demonstração ocupada; tente novamente em alguns minutos")
        sessions[key] = {"created": now, "runs": {}, "ledger": {}}
    return sessions[key]


def identity(run):
    return "12345678000195:43:1" if run["scenario"] == "divergence" else "12345678000195:42:1"


def event(run, step, title, message, kind="step"):
    run["events"].append({"step": step, "title": title, "message": message,
                          "kind": kind, "time": datetime.now(timezone.utc).isoformat()})


def snapshot(state, run):
    ledger = state["ledger"].get(identity(run))
    return {"id": run["id"], "scenario": run["scenario"], "status": run["status"],
            "step": run["step"], "steps": STEPS, "events": list(run["events"]),
            "source": {"name": "NovaTech ERP · origem", "order": "CP-2026-0043" if run["scenario"] == "divergence" else "CP-2026-0042",
                       "amount": str(run.get("source_amount", Decimal("150.00") if run["scenario"] == "divergence" else Decimal("123.45"))),
                       "status": "Revisão necessária" if run["status"] == "needs_review" else "Cenário de demonstração"},
            "destination": {"name": "Orbit Finance · destino", "entries": 1 if ledger else 0,
                            "protocol": ledger["protocol"] if ledger else None,
                            "amount": ledger["amount"] if ledger else None},
            "invoice": run.get("invoice"), "temporary": True,
            "elapsed_seconds": round(max(0, run.get("finished", monotonic()) - run["started"]), 3),
            "expires_in_seconds": max(0, int(TTL - (monotonic() - state["created"])))}


@router.post("/runs", status_code=201)
def create_run(x_demo_session: UUID = Header(...),
               scenario: Literal["success", "divergence", "duplicate"] = Query("success")):
    # Valores default também suportam os testes diretos, sem resolução do FastAPI.
    if not isinstance(scenario, str):
        scenario = "success"
    with lock:
        state = context(x_demo_session, create=True)
        if scenario == "duplicate" and "12345678000195:42:1" not in state["ledger"]:
            raise HTTPException(409, "Conclua primeiro o cenário de sucesso para testar a duplicidade")
        if len(state["runs"]) >= MAX_RUNS:
            raise HTTPException(429, "Limite de cinco demonstrações nesta sessão temporária")
        run = {"id": str(uuid4()), "scenario": scenario, "step": 0, "status": "running",
               "events": [], "started": monotonic()}
        state["runs"][run["id"]] = run
        return snapshot(state, run)


@router.get("/summary")
def summary(x_demo_session: UUID = Header(...)):
    with lock:
        state = context(x_demo_session, create=True)
        runs = list(state["runs"].values())
        completed = [r for r in runs if r["status"] == "completed"]
        return {"runs": [snapshot(state, run) for run in reversed(runs)],
                "metrics": {"total": len(runs), "completed": len(completed),
                            "needs_review": sum(r["status"] == "needs_review" for r in runs),
                            "duplicate": sum(r["status"] == "duplicate" for r in runs),
                            "rejected": sum(r["status"] == "rejected" for r in runs),
                            "registered_amount": str(sum((Decimal(e["amount"]) for e in state["ledger"].values()), Decimal("0.00"))),
                            "average_completed_seconds": round(sum(r["finished"] - r["started"] for r in completed) / len(completed), 3) if completed else None},
                "remaining_runs": MAX_RUNS - len(runs), "temporary": True,
                "expires_in_seconds": max(0, int(TTL - (monotonic() - state["created"])))}


@router.post("/runs/{run_id}/advance")
def advance(run_id: UUID, expected_step: int, x_demo_session: UUID = Header(...)):
    with lock:
        state = context(x_demo_session)
        run = state["runs"].get(str(run_id))
        if run is None:
            raise HTTPException(404, "Execução expirada ou não encontrada nesta sessão")
        if run["status"] != "running" or run["step"] != expected_step:
            return snapshot(state, run)
        step = run["step"]
        key = identity(run)
        if step == 0:
            sample = SAMPLE.with_name("nota-divergente.pdf") if run["scenario"] == "divergence" else SAMPLE
            run["invoice"] = extract_invoice(sample.read_bytes()).model_dump(mode="json")
            message = f'PDF fictício lido: nota {run["invoice"]["number"]}, série 1 e CNPJ válido.'
        elif step == 1:
            run["source_amount"] = Decimal("150.00") if run["scenario"] == "divergence" else Decimal("123.45")
            message = "Conta a pagar encontrada no adaptador de origem."
        elif step == 2:
            if Decimal(run["invoice"]["amount"]) != run["source_amount"]:
                run["status"] = "needs_review"
                message = f'Divergência: nota {run["invoice"]["amount"]}, origem {run["source_amount"]}. Lançamento bloqueado até revisão.'
            else:
                message = "R$ 123,45 na nota e na origem: conferência aprovada."
        elif step == 3:
            if key in state["ledger"]:
                run["status"] = "duplicate"
                message = "Nota já registrada nesta sessão: novo lançamento bloqueado. Protocolo original preservado."
            else:
                state["ledger"][key] = {"protocol": "DEMO-" + uuid4().hex[:8].upper(), "amount": run["invoice"]["amount"]}
                message = "Lançamento criado no adaptador de destino, em memória."
        elif step == 4:
            entry = state["ledger"].get(key)
            if entry is None or entry["amount"] != run["invoice"]["amount"]:
                run["status"] = "needs_review"
                message = "Confirmação falhou: revisão necessária."
            else:
                message = "Destino consultado novamente: valor e protocolo confirmados."
        else:
            run["status"] = "completed"
            message = "Fluxo finalizado com eventos e protocolo de demonstração."
        event(run, step, STEPS[step], message)
        run["step"] += 1
        if run["status"] in {"completed", "duplicate"}:
            run["finished"] = monotonic()
        return snapshot(state, run)


class ReviewDecision(BaseModel):
    action: Literal["approve", "reject"]
    expected_step: int = Field(ge=0, le=6)
    reason: str = Field(min_length=10, max_length=300, pattern=r"\S")
    corrected_source_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


@router.post("/runs/{run_id}/review")
def review(run_id: UUID, decision: ReviewDecision, x_demo_session: UUID = Header(...)):
    with lock:
        state = context(x_demo_session)
        run = state["runs"].get(str(run_id))
        if run is None:
            raise HTTPException(404, "Execução expirada ou não encontrada nesta sessão")
        if run["status"] != "needs_review" or run["step"] != decision.expected_step or run["step"] != 3:
            raise HTTPException(409, "Esta execução não está aguardando revisão de valores nesta etapa")
        if len(decision.reason.strip()) < 10:
            raise HTTPException(422, "Informe uma justificativa com pelo menos dez caracteres")
        if decision.action == "reject":
            run["status"] = "rejected"
            run["finished"] = monotonic()
            event(run, 2, "Revisão humana: rejeitada", decision.reason.strip(), "review")
        else:
            if decision.corrected_source_amount != Decimal(run["invoice"]["amount"]):
                raise HTTPException(422, "O valor corrigido da origem deve coincidir com o valor da nota")
            previous = run["source_amount"]
            run["source_amount"] = decision.corrected_source_amount
            run["status"] = "running"
            event(run, 2, "Revisão humana: aprovada", f'Origem corrigida de {previous} para {decision.corrected_source_amount}. Justificativa: {decision.reason.strip()}', "review")
        return snapshot(state, run)
