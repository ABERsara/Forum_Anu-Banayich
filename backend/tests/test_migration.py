import os, tempfile
from pathlib import Path
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect, pool

import app.core.config as _cfg

BACKEND_DIR = Path(__file__).parent.parent  # backend/
EXPECTED_TABLES = {
    "users",
    "forum_posts",
    "direct_messages",
    "professional_queries",
    "reports",
    "documents",
    "audit_logs",
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

    assert EXPECTED_TABLES <= actual_tables, (
        f"Missing tables: {EXPECTED_TABLES - actual_tables}"
    )
