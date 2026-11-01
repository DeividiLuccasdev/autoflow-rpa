"""describe Acesso, listagem e auditoria por rotas reais."""
import pytest
from helpers import payload, counts

@pytest.mark.parametrize("key",[None,"wrong"])
def test_quando_chave_ausente_ou_invalida_entao_bloqueia(spec,key):
    http=spec["http"]; http.headers.pop("X-API-Key",None)
    if key: http.headers["X-API-Key"]=key
    assert http.get("/api/v1/invoices").status_code==401
    assert http.get("/api/v1/executions").status_code==401
    assert http.post("/api/v1/invoices",json=payload()).status_code==401
    assert counts(spec)==[0,0,0,0]

def test_quando_configuracao_sem_chave_entao_falha_fechado(spec,monkeypatch):
    monkeypatch.delenv("AUTOFLOW_API_KEY")
    assert spec["http"].get("/api/v1/invoices").status_code==503
    assert counts(spec)==[0,0,0,0]

def test_quando_registro_nao_existe_entao_404(spec):
    for path in ["/api/v1/invoices/missing/events","/api/v1/executions/missing"]:
        assert spec["http"].get(path).status_code==404

def test_quando_paginacao_valida_entao_respeita_ordem_limite_e_offset(spec):
    http=spec["http"]
    for number in ["42","43","44"]:
        assert http.post("/api/v1/invoices",json=payload(number=number)).status_code==201
    assert [r["number"] for r in http.get("/api/v1/invoices?limit=1&offset=1").json()]==["43"]

@pytest.mark.parametrize("query",["limit=0","limit=101","offset=-1","limit=abc"])
def test_quando_paginacao_invalida_entao_422(spec,query):
    assert spec["http"].get("/api/v1/invoices?"+query).status_code==422

def test_quando_origem_externa_entao_nao_grava(spec):
    response=spec["http"].post("/api/v1/invoices",json=payload(),headers={"Origin":"https://attacker.example"})
    assert response.status_code==403
    assert counts(spec)==[0,0,0,0]

def test_quando_resposta_privada_entao_nao_permite_cache(spec):
    assert spec["http"].get("/api/v1/invoices").headers["Cache-Control"]=="no-store"
