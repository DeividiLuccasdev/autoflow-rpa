"""describe Sessões públicas: estado real em memória, sem mock ou banco fictício."""

from time import monotonic
from uuid import uuid4

from helpers import counts, simultaneous, upload

from app.demo.automation import lock, sessions


def test_quando_pdf_publico_canonico_entao_extrai_sem_gravar(spec):
    http = spec["http"]
    http.headers.pop("X-API-Key")
    content = http.get("/demo/sample").content
    response = upload(http, content, path="/demo/analyze")
    assert response.status_code == 200
    assert response.json()["persisted"] is False
    assert response.json()["invoice"]["amount"] == "123.45"
    assert counts(spec) == [0, 0, 0, 0]
    assert upload(http, b"%PDF-untrusted", path="/demo/analyze").status_code == 422


def test_quando_duas_requisicoes_mesma_etapa_entao_avanca_uma_vez(spec):
    http = spec["http"]
    headers = {"X-Demo-Session": str(uuid4())}
    run = http.post("/demo/automation/runs", headers=headers).json()
    path = f"/demo/automation/runs/{run['id']}/advance?expected_step=0"
    responses = simultaneous(*[lambda: http.post(path, headers=headers) for _ in range(2)])
    assert all(r.status_code == 200 and r.json()["step"] == 1 and len(r.json()["events"]) == 1 for r in responses)
    assert http.post(path, headers=headers).json()["step"] == 1


def test_quando_sessao_b_tenta_execucao_a_entao_nao_acessa(spec):
    http = spec["http"]
    a = {"X-Demo-Session": str(uuid4())}
    b = {"X-Demo-Session": str(uuid4())}
    run = http.post("/demo/automation/runs", headers=a).json()
    path = f"/demo/automation/runs/{run['id']}/advance?expected_step=0"
    assert http.post(path, headers=b).status_code == 404
    assert http.post(path, headers=a).json()["step"] == 1


def test_quando_sessao_preexistente_expirada_entao_nao_continua(spec):
    http = spec["http"]
    key = str(uuid4())
    headers = {"X-Demo-Session": key}
    run = http.post("/demo/automation/runs", headers=headers).json()
    # Fixture de sessão antiga, sem substituir relógio ou regra de expiração.
    with lock:
        sessions[key]["created"] = monotonic() - 901
    assert http.post(f"/demo/automation/runs/{run['id']}/advance?expected_step=0", headers=headers).status_code == 404


def test_quando_execucao_completa_repetida_entao_um_lancamento(spec):
    http = spec["http"]
    headers = {"X-Demo-Session": str(uuid4())}
    first = http.post("/demo/automation/runs", headers=headers).json()
    for step in range(6):
        first = http.post(f"/demo/automation/runs/{first['id']}/advance?expected_step={step}", headers=headers).json()
    assert first["status"] == "completed" and len(first["events"]) == 6
    second = http.post("/demo/automation/runs", headers=headers).json()
    for step in range(4):
        second = http.post(f"/demo/automation/runs/{second['id']}/advance?expected_step={step}", headers=headers).json()
    assert second["status"] == "duplicate"
    assert second["destination"] == first["destination"]
    assert counts(spec) == [0, 0, 0, 0]


def test_quando_cinco_execucoes_entao_recusa_a_sexta(spec):
    http = spec["http"]
    headers = {"X-Demo-Session": str(uuid4())}
    for _ in range(5):
        assert http.post("/demo/automation/runs", headers=headers).status_code == 201
    assert http.post("/demo/automation/runs", headers=headers).status_code == 429


def test_quando_excesso_por_ip_entao_429_mesmo_trocando_forwarded_for(spec):
    http = spec["http"]
    for i in range(15):
        assert (
            http.post(
                "/demo/automation/runs", headers={"X-Demo-Session": str(uuid4()), "X-Forwarded-For": f"192.0.2.{i}"}
            ).status_code
            == 201
        )
    response = http.post(
        "/demo/automation/runs", headers={"X-Demo-Session": str(uuid4()), "X-Forwarded-For": "192.0.2.200"}
    )
    assert response.status_code == 429 and response.headers["Retry-After"] == "60"


def test_quando_capacidade_cheia_entao_preserva_sessoes_ativas(spec):
    # Massa de dados de sessões ativas, sem trocar o limite ou a regra de negócio.
    keys = [str(uuid4()) for _ in range(128)]
    with lock:
        for key in keys:
            sessions[key] = {"created": monotonic(), "runs": {}, "ledger": {}}
    response = spec["http"].post("/demo/automation/runs", headers={"X-Demo-Session": str(uuid4())})
    assert response.status_code == 429
    with lock:
        assert list(sessions) == keys


def test_quando_corpo_publico_excede_limite_entao_rejeita(spec):
    response = upload(spec["http"], b"x" * (128 * 1024 + 1), path="/demo/analyze")
    assert response.status_code == 413
    assert counts(spec) == [0, 0, 0, 0]
