"""Banco explícito de testes, com schema isolado por caso."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from test_documents import pdf

from app.db import Base
from app.executions import enqueue, process_execution, reserve_dispatch
from app.models import AuditEvent, Execution, Invoice


@pytest.fixture
def postgres():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL não configurada")
    schema = "test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url, connect_args={"options": f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000"}
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def parallel(actions):
    barrier = Barrier(len(actions))

    def run(action):
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))


def test_concurrent_upload_same_document(postgres):
    content = pdf()

    def upload():
        with postgres() as db:
            return enqueue(db, content).id

    assert len(set(parallel([upload, upload]))) == 1


def test_concurrent_workers_same_execution(postgres):
    with postgres() as db:
        execution_id = enqueue(db, pdf()).id

    def process():
        with postgres() as db:
            process_execution(db, execution_id)

    parallel([process, process])
    with postgres() as db:
        assert db.get(Execution, execution_id).status == "completed"
        assert len(db.scalars(select(Invoice)).all()) == 1
        assert len(db.scalars(select(AuditEvent)).all()) == 2


def test_different_documents_same_invoice(postgres):
    with postgres() as db:
        first = enqueue(db, pdf()).id
        second = enqueue(db, pdf() + b"\n%distinct").id

    def process(execution_id):
        with postgres() as db:
            process_execution(db, execution_id)

    parallel([lambda: process(first), lambda: process(second)])
    with postgres() as db:
        assert sorted(db.scalars(select(Execution.status)).all()) == ["completed", "duplicate"]
        assert len(db.scalars(select(Invoice)).all()) == 1


def test_concurrent_dispatch_reserves_once(postgres):
    from datetime import datetime, timedelta

    with postgres() as db:
        execution_id = enqueue(db, pdf()).id
    now = datetime.now(UTC) + timedelta(seconds=1)

    def reserve():
        with postgres() as db:
            return reserve_dispatch(db, execution_id, now)

    assert sorted(parallel([reserve, reserve])) == [False, True]


def test_postgres_migrations(postgres):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    engine = postgres.kw["bind"]
    # Somente o schema efêmero criado pela fixture deste teste.
    Base.metadata.drop_all(engine)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
    with postgres() as db:
        execution = enqueue(db, pdf())
        process_execution(db, execution.id)
        assert db.get(Execution, execution.id).status == "completed"
