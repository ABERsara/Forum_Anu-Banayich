import os
import tempfile
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, pool

import app.core.config as _cfg
import app.models  # noqa: F401  — registers every model on Base.metadata
from app.db.base import Base

BACKEND_DIR = Path(__file__).parent.parent  # backend/
EXPECTED_TABLES = {
    "users",
    "forum_posts",
    "direct_messages",
    "professional_queries",
    "reports",
    "documents",
    "audit_logs",
    "agent_domains",
    "agent_knowledge_entries",
    "agent_conversations",
    "agent_messages",
}


def test_migration_creates_all_tables(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_migration.db")
        db_url = f"sqlite:///{db_path}"

        # env.py overrides sqlalchemy.url from settings.DATABASE_URL — patch it here
        monkeypatch.setattr(_cfg.settings, "DATABASE_URL", db_url)

        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        command.upgrade(alembic_cfg, "head")

        engine = create_engine(db_url, poolclass=pool.NullPool)
        actual_tables = set(inspect(engine).get_table_names())
        engine.dispose()  # release file lock before tempdir cleanup (Windows)

    assert actual_tables >= EXPECTED_TABLES, (
        f"Missing tables: {EXPECTED_TABLES - actual_tables}"
    )


def test_no_agent_model_migration_drift(monkeypatch) -> None:
    """The agent tables' migration (79daa6708dd8) must produce exactly the
    schema `models/agent.py` describes. Otherwise the next
    `alembic revision --autogenerate` silently emits DROP/ADD for the drift
    (e.g. an index created in a migration but never declared on the model).

    Scoped to the agent tables on purpose: this guards ABF-120's own schema.
    Pre-existing repo-wide drift in unrelated tables is out of scope here (and
    is reported to the team separately)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_url = f"sqlite:///{os.path.join(tmp_dir, 'drift.db')}"
        monkeypatch.setattr(_cfg.settings, "DATABASE_URL", db_url)

        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(db_url, poolclass=pool.NullPool)
        try:
            with engine.connect() as connection:
                context = MigrationContext.configure(connection)
                diff = compare_metadata(context, Base.metadata)
        finally:
            engine.dispose()

    agent_drift = [entry for entry in diff if "agent_" in repr(entry)]
    assert not agent_drift, f"agent model/migration drift detected: {agent_drift}"
