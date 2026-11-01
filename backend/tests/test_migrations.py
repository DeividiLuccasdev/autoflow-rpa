from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

def test_upgrade_preserves_legacy_execution(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
        connection.execute(text("INSERT INTO executions (id, sha256, content, status, created_at) VALUES (:id, :sha, :content, 'queued', CURRENT_TIMESTAMP)"), {"id": "legacy", "sha": "a" * 64, "content": b"%PDF-demo"})
        connection.commit()
        command.upgrade(config, "head")
        result = connection.execute(text("SELECT status, dispatch_attempts, next_dispatch_at, content FROM executions WHERE id='legacy'")).one()
        assert result.status == "queued"
        assert result.dispatch_attempts == 0
        assert result.next_dispatch_at is not None
        assert result.content == b"%PDF-demo"
        assert "next_dispatch_at" in {c["name"] for c in inspect(connection).get_columns("executions")}
    engine.dispose()
