"""Cenários públicos: decisões, isolamento, idempotência e métricas reais."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from test_invoices import client


def start(http, headers, scenario="success"):
    response = http.post('/demo/automation/runs', params={"scenario": scenario}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def proceed(http, headers, run):
    while run["status"] == "running":
        response = http.post(f'/demo/automation/runs/{run["id"]}/advance', params={"expected_step":run["step"]}, headers=headers)
        assert response.status_code == 200, response.text
        run = response.json()
    return run


def decision(http, headers, run, **changes):
    payload = {"action":"approve", "expected_step":run["step"], "reason":"Conferido no documento de origem.", "corrected_source_amount":"123.45", **changes}
    return http.post(f'/demo/automation/runs/{run["id"]}/review', json=payload, headers=headers)


def test_divergence_blocks_then_review_resumes_and_audits(client):
    http, _ = client
    headers = {"X-Demo-Session":str(uuid4())}
    run = proceed(http, headers, start(http, headers, "divergence"))
    assert run["invoice"]["number"] == "43"
    assert run["status"] == "needs_review" and run["step"] == 3
    assert run["source"]["amount"] == "150.00" and run["destination"]["entries"] == 0
    before = http.get('/demo/automation/summary',headers=headers).json()
    assert before["metrics"]["needs_review"] == 1
    assert before["metrics"]["registered_amount"] == "0.00"
    # Tentar avançar sem decisão não produz efeitos no destino.
    blocked = http.post(f'/demo/automation/runs/{run["id"]}/advance?expected_step=3',headers=headers).json()
    assert blocked["status"] == "needs_review" and blocked["destination"]["entries"] == 0
    reviewed = decision(http, headers, run)
    assert reviewed.status_code == 200
    assert reviewed.json()["source"]["amount"] == "123.45"
    # Reenvio da decisão não cria um segundo evento nem um novo lançamento.
    assert decision(http, headers, run).status_code == 409
    result = proceed(http,headers,reviewed.json())
    assert result["status"] == "completed" and result["destination"]["entries"] == 1
    audits = [e for e in result["events"] if e["kind"] == "review"]
    assert len(audits) == 1 and "150.00" in audits[0]["message"]
    metrics = http.get('/demo/automation/summary',headers=headers).json()["metrics"]
    assert metrics["completed"] == 1 and metrics["needs_review"] == 0
    assert metrics["registered_amount"] == "123.45"
    assert metrics["average_completed_seconds"] >= 0


def test_rejected_document_never_registers(client):
    http, _ = client; headers = {"X-Demo-Session":str(uuid4())}
    run = proceed(http,headers,start(http,headers,"divergence"))
    response = decision(http,headers,run,action="reject",corrected_source_amount=None)
    assert response.status_code == 200 and response.json()["status"] == "rejected"
    assert response.json()["destination"]["entries"] == 0
    assert decision(http,headers,run).status_code == 409
    metrics = http.get('/demo/automation/summary',headers=headers).json()["metrics"]
    assert metrics["rejected"] == 1 and metrics["registered_amount"] == "0.00"


@pytest.mark.parametrize("changes", [
    {"reason":"curta"}, {"reason":" " * 20}, {"corrected_source_amount":"150.00"},
    {"corrected_source_amount":"123.451"}, {"corrected_source_amount":None},
    {"corrected_source_amount":"-1"}, {"action":"bypass"},
])
def test_invalid_review_keeps_pending_and_destination_empty(client,changes):
    http,_ = client; headers = {"X-Demo-Session":str(uuid4())}
    run = proceed(http,headers,start(http,headers,"divergence"))
    assert decision(http,headers,run,**changes).status_code == 422
    item = http.get('/demo/automation/summary',headers=headers).json()["runs"][0]
    assert item["status"] == "needs_review" and item["destination"]["entries"] == 0


def test_review_is_session_scoped_and_requires_pending_state(client):
    http,_ = client; headers = {"X-Demo-Session":str(uuid4())}
    run = start(http,headers,"divergence")
    assert decision(http,headers,run).status_code == 409
    run = proceed(http,headers,run)
    assert decision(http,{"X-Demo-Session":str(uuid4())},run).status_code == 404
    assert decision(http,headers,run,expected_step=2).status_code == 409


def test_duplicate_preserves_protocol_and_amount_once(client):
    http,_ = client; headers = {"X-Demo-Session":str(uuid4())}
    assert http.post('/demo/automation/runs?scenario=duplicate',headers=headers).status_code == 409
    first = proceed(http,headers,start(http,headers))
    second = proceed(http,headers,start(http,headers,"duplicate"))
    assert second["status"] == "duplicate"
    assert second["destination"] == first["destination"]
    data = http.get('/demo/automation/summary',headers=headers).json()
    assert data["metrics"]["total"] == 2 and data["metrics"]["duplicate"] == 1
    assert data["metrics"]["registered_amount"] == "123.45"
    assert data["remaining_runs"] == 3
    other = http.get('/demo/automation/summary',headers={"X-Demo-Session":str(uuid4())}).json()
    assert other["runs"] == [] and other["metrics"]["average_completed_seconds"] is None


def test_concurrent_decisions_have_one_winner(client):
    http,_ = client; headers = {"X-Demo-Session":str(uuid4())}
    run = proceed(http,headers,start(http,headers,"divergence"))
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda action:decision(http,headers,run,action=action),["approve","reject"]))
    assert sorted(response.status_code for response in results) == [200,409]
    current = http.get('/demo/automation/summary',headers=headers).json()["runs"][0]
    assert len([e for e in current["events"] if e["kind"] == "review"]) == 1


def test_both_documents_have_distinct_identity_and_metrics(client):
    http,_ = client; headers = {"X-Demo-Session":str(uuid4())}
    first = proceed(http,headers,start(http,headers))
    pending = proceed(http,headers,start(http,headers,"divergence"))
    second = proceed(http,headers,decision(http,headers,pending).json())
    assert first["destination"]["protocol"] != second["destination"]["protocol"]
    metrics = http.get('/demo/automation/summary',headers=headers).json()["metrics"]
    assert metrics["completed"] == 2 and metrics["registered_amount"] == "246.90"


def test_unknown_scenario_is_rejected(client):
    assert client[0].post('/demo/automation/runs?scenario=arbitrary',headers={"X-Demo-Session":str(uuid4())}).status_code == 422
