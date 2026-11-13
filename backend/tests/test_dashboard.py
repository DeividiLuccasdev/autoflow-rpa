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


def test_pages_version_assets_by_content_hash(client):
    import hashlib
    import re

    from app.config import STATIC_DIR

    http, _ = client
    for path, asset in [("/", "app.js"), ("/workspace", "workspace.js"), ("/assistente", "assistant.js")]:
        html = http.get(path).text
        expected = hashlib.sha256((STATIC_DIR / asset).read_bytes()).hexdigest()[:10]
        assert f"/assets/{asset}?v={expected}" in html
        # Nenhuma referência local fica sem versão.
        assert not re.search(r"/assets/[\w.-]+\.(?:css|js)(?!\?v=)", html)
