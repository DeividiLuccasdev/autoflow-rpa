"""Request specs: rotas reais, PostgreSQL migrado e serviços externos reais."""

import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app

BACKEND = Path(__file__).resolve().parents[2]


def test_database_url():
    raw = os.getenv("TEST_POSTGRES_URL")
    if not raw:
        pytest.fail(
            "TEST_POSTGRES_URL obrigatória; execute python scripts/test_all.py. Nenhum fallback ou skip.", pytrace=False
        )
    url = make_url(raw)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"127.0.0.1", "localhost", "postgres", "request-db"}
        or not url.database
        or not url.database.endswith("_test")
    ):
        pytest.fail("Banco recusado: use PostgreSQL local/container com nome terminado em _test", pytrace=False)
    return url


@pytest.fixture
def spec(tmp_path, monkeypatch):
    from app.demo.automation import lock, sessions
    from app.http_security import limiter

    limiter.clear()
    with lock:
        sessions.clear()
    monkeypatch.setenv("AUTOFLOW_API_KEY", "request-spec-" + "x" * 40)
    monkeypatch.setenv("AUTOFLOW_ASYNC_ENABLED", "true")
    url = test_database_url()
    schema = "request_" + uuid4().hex
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated_url = url.update_query_dict(
        {"options": f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000"}
    )
    engine = create_engine(isolated_url, hide_parameters=True, pool_size=8)
    config = Config(str(BACKEND / "alembic.ini"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    factory = sessionmaker(bind=engine)

    def database():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database  # Injeção de conexão real, não mock.
    with TestClient(app, raise_server_exceptions=False) as client:
        client.headers["X-API-Key"] = "request-spec-" + "x" * 40
        yield {
            "http": client,
            "factory": factory,
            "engine": engine,
            "url": isolated_url,
            "schema": schema,
            "tmp": tmp_path,
        }
    app.dependency_overrides.clear()
    engine.dispose()
    with admin.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


@pytest.fixture
def live_queue(spec):
    from urllib.parse import urlsplit

    import redis

    raw = os.getenv("TEST_REDIS_URL")
    if not raw:
        pytest.fail("TEST_REDIS_URL obrigatória para fila real; nenhum mock ou skip", pytrace=False)
    parsed = urlsplit(raw)
    if parsed.hostname not in {"127.0.0.1", "localhost", "redis", "request-redis"} or parsed.path != "/15":
        pytest.fail("Redis recusado: use serviço de teste local/container no banco 15", pytrace=False)
    broker = redis.Redis.from_url(raw)
    broker.ping()
    prefix = spec["schema"] + ":"
    environment = {
        **os.environ,
        "DATABASE_URL": spec["url"].render_as_string(hide_password=False),
        "REDIS_URL": raw,
        "REQUEST_QUEUE": spec["schema"],
        "REQUEST_PREFIX": prefix,
        "PYTHONPATH": os.pathsep.join([str(BACKEND), str(Path(__file__).parent)]),
    }
    processes = []
    logs = []

    def start(workers=1, broker_url=None):
        process_env = {**environment, "REDIS_URL": broker_url or raw}
        commands = [
            (
                f"worker-{i}",
                [
                    "worker",
                    "--pool=solo",
                    "--concurrency=1",
                    "--loglevel=warning",
                    "--hostname",
                    f"{spec['schema']}-{i}@%h",
                ],
            )
            for i in range(workers)
        ]
        commands.append(("beat", ["beat", "--loglevel=warning", "--schedule", str(spec["tmp"] / "beat-schedule")]))
        for name, arguments in commands:
            log = (spec["tmp"] / f"{name}.log").open("ab")
            logs.append(log)
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-m", "celery", "-A", "worker_app:celery_app", *arguments],
                    cwd=BACKEND,
                    env=process_env,
                    stdout=log,
                    stderr=log,
                )
            )
        time.sleep(1)
        assert all(p.poll() is None for p in processes), "Worker/beat encerraram; consulte os logs do teste"

    spec["start_queue"] = start
    spec["redis_url"] = raw
    spec["prefix"] = prefix
    spec["redis"] = broker
    try:
        yield spec
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in logs:
            log.close()
        keys = list(broker.scan_iter(match=prefix + "*"))
        if keys:
            broker.delete(*keys)
        broker.close()


def wait_execution(http, execution_id, states, timeout=30):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        response = http.get(f"/api/v1/executions/{execution_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in states:
            return last
        time.sleep(1)
    pytest.fail(f"Execução não chegou a {states}; último resultado: {last}")
