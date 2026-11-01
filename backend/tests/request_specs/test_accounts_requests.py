"""describe Contas: HTTP, PostgreSQL migrado e sessões reais, sem mocks."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from app.main import app
from app.models import User, Invitation, LoginSession, Invoice, Document, Execution
from helpers import counts, payload, pdf, upload, simultaneous
from conftest import wait_execution

PASSWORD = "Frase exclusiva de teste 2026!"

def invitation(spec, email="a@example.test"):
    response = spec["http"].post("/auth/invitations", json={"email": email})
    assert response.status_code == 201
    return response.json()["invitation"]

def activate(spec, email="a@example.test"):
    token = invitation(spec, email)
    response = spec["http"].post("/auth/register", json={"email": email, "password": PASSWORD, "invitation": token})
    assert response.status_code == 201
    return token

@contextmanager
def account(spec, email="a@example.test"):
    activate(spec, email)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield client

def test_quando_convite_valido_entao_ativa_sem_expor_segredos(spec):
    token = invitation(spec, "A@Example.test")
    response = spec["http"].post("/auth/register", json={"email": "a@example.test", "password": PASSWORD, "invitation": token})
    assert response.status_code == 201
    assert PASSWORD not in response.text and token not in response.text
    with spec["factory"]() as db:
        user = db.scalar(select(User))
        assert user.email == "a@example.test" and user.password_hash != PASSWORD
        assert user.password_hash.startswith("pbkdf2_sha256$600000$")
        invite = db.scalar(select(Invitation))
        assert invite.token_hash != token and invite.consumed_at

def test_quando_sem_convite_entao_nao_cria_conta(spec):
    response = spec["http"].post("/auth/register", json={"email": "a@example.test", "password": PASSWORD, "invitation": "x"*43})
    assert response.status_code == 400
    with spec["factory"]() as db:
        assert db.scalar(select(User)) is None

def test_quando_convite_expirou_ou_email_diverge_entao_rejeita(spec):
    token = invitation(spec)
    assert spec["http"].post("/auth/register", json={"email": "b@example.test", "password": PASSWORD, "invitation": token}).status_code == 400
    with spec["engine"].begin() as db:
        db.execute(text("UPDATE invitations SET expires_at=:past"), {"past": datetime.now(timezone.utc)-timedelta(seconds=1)})
    assert spec["http"].post("/auth/register", json={"email": "a@example.test", "password": PASSWORD, "invitation": token}).status_code == 400

def test_quando_duas_ativacoes_simultaneas_entao_convite_usado_uma_vez(spec):
    token = invitation(spec)
    body = {"email": "a@example.test", "password": PASSWORD, "invitation": token}
    responses = simultaneous(*[lambda: spec["http"].post("/auth/register", json=body) for _ in range(2)])
    assert sorted(r.status_code for r in responses) == [201, 400]
    with spec["factory"]() as db:
        assert len(db.scalars(select(User)).all()) == 1
    assert spec["http"].post("/auth/register", json=body).status_code == 400

def test_quando_senha_curta_entao_nao_expoe_senha_nem_consumo(spec):
    token = invitation(spec)
    response = spec["http"].post("/auth/register", json={"email": "a@example.test", "password": "segredo-curto", "invitation": token})
    assert response.status_code == 422 and "segredo-curto" not in response.text and token not in response.text
    with spec["factory"]() as db:
        assert db.scalar(select(Invitation)).consumed_at is None

def test_quando_login_valido_entao_cookie_http_only_e_sessao_hash(spec):
    activate(spec)
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/auth/login", json={"email":"a@example.test", "password":PASSWORD})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie and "secure" in cookie
        assert client.get("/auth/me").json()["email"] == "a@example.test"
        with spec["factory"]() as db:
            session = db.scalar(select(LoginSession))
            assert session.token_hash != client.cookies.get("autoflow_session")
        assert "password" not in response.text and "token_hash" not in response.text

def test_quando_senha_ou_email_invalido_entao_mesma_mensagem(spec):
    activate(spec)
    responses = [spec["http"].post("/auth/login", json={"email": email, "password": "incorreta"}) for email in ["a@example.test", "missing@example.test"]]
    assert [r.status_code for r in responses] == [401, 401]
    assert responses[0].json() == responses[1].json()

def test_quando_excesso_login_entao_limita_sem_confiar_em_forwarded_for(spec):
    for i in range(10):
        assert spec["http"].post("/auth/login", json={"email":"a@example.test","password":"wrong"}, headers={"X-Forwarded-For":f"192.0.2.{i}"}).status_code == 401
    response = spec["http"].post("/auth/login", json={"email":"a@example.test","password":"wrong"})
    assert response.status_code == 429 and response.headers["Retry-After"] == "60"

def test_quando_logout_entao_cookie_antigo_nao_autentica(spec):
    with account(spec) as a:
        token = a.cookies.get("autoflow_session")
        assert a.post("/auth/logout").status_code == 204
        assert a.get("/api/v1/invoices").status_code == 401
        a.cookies.set("autoflow_session", token)
        assert a.get("/api/v1/invoices").status_code == 401

def test_quando_sessao_expira_entao_bloqueia_leitura_e_escrita(spec):
    with account(spec) as a:
        with spec["engine"].begin() as db:
            db.execute(text("UPDATE login_sessions SET expires_at=:past"), {"past":datetime.now(timezone.utc)-timedelta(seconds=1)})
        assert a.get("/api/v1/invoices").status_code == 401
        assert a.post("/api/v1/invoices", json=payload()).status_code == 401
        assert counts(spec) == [0,0,0,0]

def test_quando_sem_csrf_ou_origem_externa_entao_nao_grava(spec):
    with account(spec) as a:
        csrf = a.headers.pop("X-CSRF-Token")
        assert a.post("/api/v1/invoices", json=payload()).status_code == 403
        a.headers["X-CSRF-Token"] = csrf
        assert a.post("/api/v1/invoices", json=payload(), headers={"Origin":"https://evil.example"}).status_code == 403
        assert counts(spec) == [0,0,0,0]

def test_quando_a_salva_entao_b_nao_le_nota_auditoria_ou_execucao(spec):
    with account(spec) as a, account(spec, "b@example.test") as b:
        note = a.post("/api/v1/invoices", json=payload()).json()
        execution = upload(a, pdf(), path="/api/v1/executions").json()
        assert len(a.get("/api/v1/invoices").json()) == 1
        assert b.get("/api/v1/invoices").json() == []
        assert b.get(f'/api/v1/invoices/{note["id"]}/events').status_code == 404
        assert b.get(f'/api/v1/executions/{execution["id"]}').status_code == 404
        assert b.get("/api/v1/executions").json() == []
        events = a.get(f'/api/v1/invoices/{note["id"]}/events').json()
        with spec["factory"]() as db:
            user = db.scalar(select(User).where(User.email == "a@example.test"))
            assert events[0]["actor"] == user.id
        # A chave operacional conserva somente o acervo legado.
        assert spec["http"].get("/api/v1/invoices").json() == []
        assert spec["http"].get(f'/api/v1/executions/{execution["id"]}').status_code == 404

def test_quando_usuarios_enviam_mesmo_pdf_entao_registros_independentes(spec):
    with account(spec) as a, account(spec, "b@example.test") as b:
        content = pdf()
        responses = simultaneous(lambda: upload(a, content), lambda: upload(b, content))
        assert [r.status_code for r in responses] == [201, 201]
        assert responses[0].json()["id"] != responses[1].json()["id"]
        assert upload(a, content).status_code == 409
        assert counts(spec) == [2,2,4,0]

def test_quando_mesmo_usuario_envia_simultaneamente_entao_um_registro(spec):
    with account(spec) as a:
        responses = simultaneous(*[lambda: a.post("/api/v1/invoices", json=payload()) for _ in range(2)])
        assert sorted(r.status_code for r in responses) == [201,409]
        assert counts(spec) == [1,0,1,0]

def test_quando_tenta_forjar_owner_ou_emitir_convite_entao_rejeita(spec):
    with account(spec) as a:
        assert a.post("/api/v1/invoices", json=payload(owner_id="legacy")).status_code == 422
        assert a.post("/auth/invitations", json={"email":"intruder@example.test"}).status_code == 403
        assert counts(spec) == [0,0,0,0]

def test_quando_novo_usuario_entao_nao_recebe_acervo_legado(spec):
    assert spec["http"].post("/api/v1/invoices", json=payload()).status_code == 201
    with account(spec) as a:
        assert a.get("/api/v1/invoices").json() == []
        assert a.post("/api/v1/invoices", json=payload()).status_code == 201
        assert len(spec["http"].get("/api/v1/invoices").json()) == 1

def test_quando_worker_processa_entao_preserva_proprietario(live_queue):
    spec = live_queue
    with account(spec) as a, account(spec, "b@example.test") as b:
        content = pdf()
        first = upload(a, content, path="/api/v1/executions")
        second = upload(b, content, path="/api/v1/executions")
        assert first.status_code == second.status_code == 202
        assert first.json()["id"] != second.json()["id"]
        spec["start_queue"](workers=2)
        one = wait_execution(a, first.json()["id"], {"completed"})
        two = wait_execution(b, second.json()["id"], {"completed"})
        assert b.get(f'/api/v1/invoices/{one["invoice_id"]}/events').status_code == 404
        assert a.get(f'/api/v1/invoices/{two["invoice_id"]}/events').status_code == 404
        assert counts(spec) == [2,2,4,2]
        with spec["factory"]() as db:
            for run in db.scalars(select(Execution)):
                assert db.get(Invoice, run.invoice_id).owner_id == run.owner_id
                assert db.scalar(select(Document).where(Document.invoice_id == run.invoice_id)).owner_id == run.owner_id

def test_quando_visitante_entao_demo_e_tela_disponiveis_mas_dados_privados_bloqueados(spec):
    with TestClient(app) as visitor:
        for path in ["/", "/workspace", "/assets/workspace.js", "/assets/workspace.css", "/demo/sample"]:
            assert visitor.get(path).status_code == 200
        assert visitor.get("/api/v1/invoices").status_code == 401
        assert visitor.get("/workspace").headers["Cache-Control"] == "no-store"
        assert visitor.post("/auth/invitations",json={"email":"a@example.test"}).status_code == 401
