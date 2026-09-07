import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, pool, text

import app.core.config as _cfg

# Imported for its side effect: app.models.__init__ imports every model module,
# and that is what attaches the tables to Base.metadata. Without it the metadata
# is empty and test_migration_creates_all_tables has nothing to compare against.
# migrations/env.py does not come through this package — it names the model
# modules one by one — so adding a model to app/models/__init__.py puts it in
# front of this test but not in front of autogenerate. That import list has to
# be extended too.
import app.models  # noqa: F401
from app.db.base import Base

BACKEND_DIR = Path(__file__).parent.parent  # backend/

# The merge revision that ABF-114's read_at migration sits directly on top of.
REVISION_BEFORE_READ_AT = "aac7e1fb8f49"


@contextmanager
def _alembic_on_a_temp_sqlite_db(monkeypatch):
    """An alembic Config pointed at a throwaway SQLite file, plus its URL."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_url = f"sqlite:///{os.path.join(tmp_dir, 'test_migration.db')}"
        # env.py overrides sqlalchemy.url from settings.DATABASE_URL — patch it here
        monkeypatch.setattr(_cfg.settings, "DATABASE_URL", db_url)

        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        yield alembic_cfg, db_url


def _created_tables(db_url: str) -> set[str]:
    """
    Every table `alembic upgrade head` left behind. alembic_version is dropped
    from the set: the migration runner creates it to record the revision, no
    model declares it, and its presence is not drift.
    """
    engine = create_engine(db_url, poolclass=pool.NullPool)
    try:
        return set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()  # release the file lock before tempdir cleanup (Windows)


def test_migration_creates_all_tables(monkeypatch) -> None:
    """
    What `alembic upgrade head` builds has to be what the models declare, read
    off Base.metadata rather than a list maintained by hand here. The hand-kept
    list is precisely what went stale: ABF-139's `likes` was never added to it,
    so deleting that migration would still have passed, and ABF-120's three
    agent tables only landed in it because whoever wrote fff7271 remembered to
    edit two files. Reading the expectation off the metadata instead covers
    every future migration for free, with nothing to keep in step here.

    Equality rather than a superset, so the drift is caught in both
    directions — a model whose migration was never written, and a table a
    migration still creates for a model that is gone.
    """
    with _alembic_on_a_temp_sqlite_db(monkeypatch) as (alembic_cfg, db_url):
        command.upgrade(alembic_cfg, "head")
        created = _created_tables(db_url)

    declared = set(Base.metadata.tables)
    missing = declared - created
    unexpected = created - declared
    assert not missing and not unexpected, (
        f"Declared by a model but created by no migration: {sorted(missing)}. "
        f"Created by a migration but declared by no model: {sorted(unexpected)}."
    )


def _direct_message_columns(db_url: str) -> set[str]:
    engine = create_engine(db_url, poolclass=pool.NullPool)
    try:
        return {c["name"] for c in inspect(engine).get_columns("direct_messages")}
    finally:
        engine.dispose()  # release the file lock before tempdir cleanup (Windows)


def _unread_index_columns(db_url: str) -> list[str]:
    engine = create_engine(db_url, poolclass=pool.NullPool)
    try:
        indexes = inspect(engine).get_indexes("direct_messages")
    finally:
        engine.dispose()
    return next(
        index["column_names"]
        for index in indexes
        if index["name"] == "ix_direct_messages_recipient_unread"
    )


def _read_state(db_url: str, column: str) -> dict[str, object]:
    """Every direct_messages row's id mapped to its read column, as stored."""
    engine = create_engine(db_url, poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT id, {column} FROM direct_messages")  # noqa: S608
            ).all()
    finally:
        engine.dispose()
    return {row[0]: row[1] for row in rows}


def test_read_at_migration_goes_down_and_up_again_cleanly(monkeypatch) -> None:
    """
    The shared Definition of Done asks for a migration that runs both ways, and
    this one is the first here that does more than add a column: it swaps
    is_read for read_at, which on SQLite means rebuilding the table, and moves
    an index onto the new column. Asserting the index too, not just the
    columns — a downgrade that restores the column but leaves the index
    pointing at a dropped one is broken in the way that only shows up later.
    """
    with _alembic_on_a_temp_sqlite_db(monkeypatch) as (alembic_cfg, db_url):
        command.upgrade(alembic_cfg, "head")
        assert "read_at" in _direct_message_columns(db_url)
        assert "is_read" not in _direct_message_columns(db_url)
        assert _unread_index_columns(db_url) == ["recipient_id", "read_at"]

        # Naming the revision rather than "-1": this says which schema state the
        # downgrade is meant to land on, and it keeps saying it however the
        # graph grows. "-1" is read relative to whatever head is at the time —
        # it walks somewhere else entirely once another migration lands on top,
        # and stops being a single step at all once a branch joins above here.
        command.downgrade(alembic_cfg, REVISION_BEFORE_READ_AT)
        assert "is_read" in _direct_message_columns(db_url)
        assert "read_at" not in _direct_message_columns(db_url)
        assert _unread_index_columns(db_url) == ["recipient_id", "is_read"]

        command.upgrade(alembic_cfg, "head")
        assert "read_at" in _direct_message_columns(db_url)


def test_read_at_migration_carries_the_read_flag_across_in_both_directions(
    monkeypatch,
) -> None:
    """
    A schema swap that loses which messages were already read would show every
    old message as unread — and, since ABF-114 shows read_at back to the
    sender, would un-read a receipt she has already seen. read_at cannot
    recover the instant a boolean never stored, so it takes created_at: a
    lower bound the row can actually prove, rather than an invented "now".
    """
    with _alembic_on_a_temp_sqlite_db(monkeypatch) as (alembic_cfg, db_url):
        command.upgrade(alembic_cfg, REVISION_BEFORE_READ_AT)

        engine = create_engine(db_url, poolclass=pool.NullPool)
        with engine.begin() as conn:
            for message_id, is_read in (("m-read", 1), ("m-unread", 0)):
                conn.execute(
                    text(
                        "INSERT INTO direct_messages (id, sender_id, recipient_id, "
                        "conversation_key, key_version, content, is_read, created_at) "
                        "VALUES (:id, 'u-1', 'u-2', 'u-1:u-2', 1, 'x', :is_read, "
                        "'2026-08-01 10:00:00')"
                    ),
                    {"id": message_id, "is_read": is_read},
                )
        engine.dispose()

        command.upgrade(alembic_cfg, "head")
        assert _read_state(db_url, "read_at") == {
            "m-read": "2026-08-01 10:00:00",
            "m-unread": None,
        }

        command.downgrade(alembic_cfg, REVISION_BEFORE_READ_AT)
        assert _read_state(db_url, "is_read") == {"m-read": 1, "m-unread": 0}
