def test_auth_required_and_wrong_key(client):
    http, _ = client
    del http.headers["X-API-Key"]
    assert http.get("/api/v1/invoices").status_code == 401
    assert http.get("/api/v1/executions").status_code == 401
    assert http.post("/api/v1/invoices", json={}).status_code == 401
    assert http.get("/api/v1/invoices", headers={"X-API-Key": "wrong"}).status_code == 401
    assert http.get("/health").status_code == 200


def test_missing_configuration_fails_closed(client, monkeypatch):
    monkeypatch.delenv("AUTOFLOW_API_KEY")
    assert client[0].get("/api/v1/invoices").status_code == 503


def test_body_limit_before_multipart(client):
    response = client[0].post("/api/v1/executions", content=b"x" * (6 * 1024 * 1024))
    assert response.status_code == 413
