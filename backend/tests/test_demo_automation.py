from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from app.demo.automation import advance, create_run


def test_automation_registers_confirms_and_blocks_duplicate(client):
    http, _ = client
    headers = {"X-Demo-Session": str(uuid4())}
    run = http.post("/demo/automation/runs", headers=headers).json()
    assert run["destination"]["entries"] == 0
    for step in range(6):
        result = http.post(f"/demo/automation/runs/{run['id']}/advance?expected_step={step}", headers=headers)
        assert result.status_code == 200
        run = result.json()
    assert run["status"] == "completed"
    assert run["destination"]["entries"] == 1
    assert run["destination"]["protocol"].startswith("DEMO-")
    assert len(run["events"]) == 6
    second = http.post("/demo/automation/runs", headers=headers).json()
    for step in range(4):
        second = http.post(f"/demo/automation/runs/{second['id']}/advance?expected_step={step}", headers=headers).json()
    assert second["status"] == "duplicate"
    assert second["destination"]["entries"] == 1


def test_sessions_isolated_and_run_budget(client):
    http, _ = client
    headers = {"X-Demo-Session": str(uuid4())}
    run = http.post("/demo/automation/runs", headers=headers).json()
    assert (
        http.post(
            f"/demo/automation/runs/{run['id']}/advance?expected_step=0", headers={"X-Demo-Session": str(uuid4())}
        ).status_code
        == 404
    )
    for _ in range(4):
        assert http.post("/demo/automation/runs", headers=headers).status_code == 201
    assert http.post("/demo/automation/runs", headers=headers).status_code == 429


def test_same_step_concurrent_requests_advance_once():
    session_id = uuid4()
    run = create_run(session_id)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: advance(
                    run_id=__import__("uuid").UUID(run["id"]), expected_step=0, x_demo_session=session_id
                ),
                range(2),
            )
        )
    assert all(result["step"] == 1 for result in results)
    assert all(len(result["events"]) == 1 for result in results)
