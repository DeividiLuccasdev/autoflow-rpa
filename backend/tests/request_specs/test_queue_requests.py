"""describe Execuções por HTTP com worker, beat, Redis e PostgreSQL reais."""
from datetime import datetime,timedelta,timezone
from celery import Celery
from sqlalchemy import text
from helpers import pdf,upload,counts,payload,simultaneous
from conftest import wait_execution

def submit(spec,content=None):
    response=upload(spec["http"],content or pdf(),path="/api/v1/executions")
    assert response.status_code==202
    return response.json()

def test_quando_fila_desabilitada_entao_nao_cria(spec,monkeypatch):
    monkeypatch.setenv("AUTOFLOW_ASYNC_ENABLED","false")
    assert upload(spec["http"],pdf(),path="/api/v1/executions").status_code==503
    assert counts(spec)==[0,0,0,0]

def test_quando_envios_simultaneos_entao_mesma_execucao(spec):
    content=pdf()
    responses=simultaneous(*[lambda:upload(spec["http"],content,path="/api/v1/executions") for _ in range(2)])
    assert all(r.status_code==202 for r in responses)
    assert responses[0].json()["id"]==responses[1].json()["id"]
    assert counts(spec)==[0,0,0,1]


def test_quando_redis_indisponivel_entao_preserva_e_processa_apos_recuperacao(live_queue):
    spec = live_queue
    # Falha temporária real: Redis suspende comandos; não há fake/mocking do broker.
    spec["redis"].execute_command("CLIENT", "PAUSE", 5000, "ALL")
    run = submit(spec)
    assert run["status"] == "queued" and counts(spec) == [0, 0, 0, 1]
    spec["redis"].ping()  # Aguarda a retomada automática do serviço real.
    spec["start_queue"]()
    wait_execution(spec["http"], run["id"], {"completed"})
    assert counts(spec) == [1, 1, 2, 1]

def test_quando_worker_real_processa_entao_conclui_e_audita(live_queue):
    spec=live_queue;run=submit(spec)
    assert run["status"]=="queued" and counts(spec)==[0,0,0,1]
    spec["start_queue"]()
    result=wait_execution(spec["http"],run["id"],{"completed"})
    assert "content" not in result and result["invoice_id"]
    assert counts(spec)==[1,1,2,1]
    events=spec["http"].get(f'/api/v1/invoices/{result["invoice_id"]}/events').json()
    assert len(events)==2 and all(e["actor"]=="worker" for e in events)

def test_quando_pdf_invalido_entao_worker_real_encaminha_revisao(live_queue):
    spec=live_queue;run=submit(spec,pdf("sem campos"));spec["start_queue"]()
    result=wait_execution(spec["http"],run["id"],{"needs_review"})
    assert result["error"] and counts(spec)==[0,0,0,1]

def test_quando_nota_existente_entao_worker_real_nao_duplica(live_queue):
    spec=live_queue
    assert spec["http"].post("/api/v1/invoices",json=payload()).status_code==201
    run=submit(spec);spec["start_queue"]()
    wait_execution(spec["http"],run["id"],{"duplicate"})
    assert counts(spec)==[1,0,1,1]

def test_quando_broker_entrega_mesma_tarefa_a_dois_workers_entao_um_efeito(live_queue):
    spec=live_queue;run=submit(spec)
    # Injeta entrega repetida na fronteira do broker real, não chama regra interna.
    sender=Celery("redelivery-test",broker=spec["redis_url"])
    sender.conf.broker_transport_options={"global_keyprefix":spec["prefix"]}
    for _ in range(2): sender.send_task("app.worker.process_document",args=[run["id"]],queue=spec["schema"])
    spec["start_queue"](workers=2)
    wait_execution(spec["http"],run["id"],{"completed"})
    import time;time.sleep(2)
    assert counts(spec)==[1,1,2,1]
    sender.close()

def test_quando_tentativas_esgotadas_entao_beat_real_encerra(live_queue):
    spec=live_queue;run=submit(spec)
    # Fixture representa pendência histórica que já consumiu as cinco tentativas.
    with spec["engine"].begin() as connection:
        connection.execute(text("UPDATE executions SET dispatch_attempts=5,next_dispatch_at=:past WHERE id=:id"),{"past":datetime.now(timezone.utc)-timedelta(seconds=1),"id":run["id"]})
    spec["start_queue"]()
    result=wait_execution(spec["http"],run["id"],{"failed"})
    assert result["dispatch_attempts"]==5 and result["finished_at"] and counts(spec)==[0,0,0,1]

def test_quando_falha_real_no_banco_entao_rollback_e_retomada(live_queue):
    spec=live_queue
    with spec["engine"].begin() as connection:
        connection.execute(text("ALTER TABLE audit_events ADD CONSTRAINT fail_worker_test CHECK (event <> 'invoice.validated')"))
    run=submit(spec);spec["start_queue"]()
    import time
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        current=spec["http"].get(f'/api/v1/executions/{run["id"]}').json()
        if current["error"]: break
        time.sleep(1)
    assert current["status"]=="queued" and current["error"]
    assert counts(spec)==[0,0,0,1]
    with spec["engine"].begin() as connection:
        connection.execute(text("ALTER TABLE audit_events DROP CONSTRAINT fail_worker_test"))
        connection.execute(text("UPDATE executions SET next_dispatch_at=:past WHERE id=:id"),{"past":datetime.now(timezone.utc)-timedelta(seconds=1),"id":run["id"]})
    wait_execution(spec["http"],run["id"],{"completed"})
    assert counts(spec)==[1,1,2,1]
