from sqlalchemy import select

from app.models import Invoice


def test_public_dashboard_and_assets(client):
    http, _ = client
    del http.headers["X-API-Key"]
    response = http.get("/")
    assert response.status_code == 200
    assert "Centro de operações" in response.text
    assert http.get("/assets/app.js").status_code == 200
    assert http.get("/demo/sample").content.startswith(b"%PDF-")
    assert http.get("/api/v1/invoices").status_code == 401


def test_demo_extracts_only_approved_sample_without_persistence(client):
    http, factory = client
    del http.headers["X-API-Key"]
    sample = http.get("/demo/sample").content
    response = http.post("/demo/analyze", files={"file": ("sample.pdf", sample, "application/pdf")})
    assert response.status_code == 200
    assert response.json()["invoice"]["amount"] == "123.45"
    assert response.json()["persisted"] is False
    with factory() as db:
        assert db.scalar(select(Invoice)) is None
    assert (
        http.post("/demo/analyze", files={"file": ("fake.pdf", b"%PDF-untrusted", "application/pdf")}).status_code
        == 422
    )
    assert http.post("/demo/analyze", files={"file": ("big.pdf", b"x" * 65537, "application/pdf")}).status_code == 413
