import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
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

# The merge revision ABF-116's user_restrictions migration sits directly on top of.
REVISION_BEFORE_RESTRICTIONS = "45019c151eb8"


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
    agent tables (reverted since, in #118) only landed in it because whoever
    wrote fff7271 remembered to edit two files. Reading the expectation off the
    metadata instead covers every future migration for free, with nothing to
    keep in step here.

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


def _restriction_indexes(db_url: str) -> set[str]:
    engine = create_engine(db_url, poolclass=pool.NullPool)
    try:
        return {i["name"] for i in inspect(engine).get_indexes("user_restrictions")}
    finally:
        engine.dispose()  # release the file lock before tempdir cleanup (Windows)


def test_user_restrictions_migration_goes_down_and_up_again_cleanly(
    monkeypatch,
) -> None:
    """
    The shared Definition of Done asks for a migration that runs both ways
    (ABF-116, a4d7c81f0e93).

    The index is asserted alongside the table, and the second upgrade is the
    point of the test rather than a formality: a downgrade that drops the
    table but leaves something of it behind — the index here, and on
    PostgreSQL the `restrictiontype` enum type, which is why the downgrade
    drops that too — fails on the way back up, not on the way down, which is
    where nobody is looking.
    """
    with _alembic_on_a_temp_sqlite_db(monkeypatch) as (alembic_cfg, db_url):
        command.upgrade(alembic_cfg, "head")
        assert "user_restrictions" in _created_tables(db_url)
        assert _restriction_indexes(db_url) == {
            "ix_user_restrictions_user_type_expires"
        }

        # Named rather than "-1": this says which schema state the downgrade is
        # meant to land on, and it keeps saying it however the graph grows.
        command.downgrade(alembic_cfg, REVISION_BEFORE_RESTRICTIONS)
        assert "user_restrictions" not in _created_tables(db_url)

        command.upgrade(alembic_cfg, "head")
        assert "user_restrictions" in _created_tables(db_url)
        assert _restriction_indexes(db_url) == {
            "ix_user_restrictions_user_type_expires"
        }


def test_no_agent_model_migration_drift(monkeypatch) -> None:
    """The agent tables' migration (79daa6708dd8) must produce exactly the
    schema `models/agent.py` describes. Otherwise the next
    `alembic revision --autogenerate` silently emits DROP/ADD for the drift
    (e.g. an index created in a migration but never declared on the model).

    Scoped to the agent tables on purpose: this guards ABF-120's own schema.
    Pre-existing repo-wide drift in unrelated tables is out of scope here (and
    is reported to the team separately)."""
    with _alembic_on_a_temp_sqlite_db(monkeypatch) as (alembic_cfg, db_url):
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


# The revision agent_knowledge_chunks sits directly on top of.
REVISION_BEFORE_CHUNKS = "a4d7c81f0e93"


def _domain_fk_ondelete(db_url: str) -> str | None:
    """The ON DELETE rule on agent_knowledge_entries.domain_id, as stored."""
    engine = create_engine(db_url, poolclass=pool.NullPool)
    try:
        foreign_keys = inspect(engine).get_foreign_keys("agent_knowledge_entries")
    finally:
        engine.dispose()
    fk = next(fk for fk in foreign_keys if fk["constrained_columns"] == ["domain_id"])
    return fk.get("options", {}).get("ondelete")


def _entry_ids(db_url: str) -> set[str]:
    engine = create_engine(db_url, poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            return {
                row[0]
                for row in conn.execute(
                    text("SELECT id FROM agent_knowledge_entries")
                ).all()
            }
    finally:
        engine.dispose()


def test_chunks_migration_goes_down_and_up_again_cleanly(monkeypatch) -> None:
    """
    ABF-121 does more than add a table: it changes the foreign key ABF-120 left
    without ON DELETE CASCADE, which on SQLite means rebuilding
    agent_knowledge_entries around it. Both directions are asserted, because a
    downgrade that drops the new table but leaves the rebuilt constraint behind
    is broken in the way that only shows up on the next upgrade.
    """
    with _alembic_on_a_temp_sqlite_db(monkeypatch) as (alembic_cfg, db_url):
        command.upgrade(alembic_cfg, "head")
        assert "agent_knowledge_chunks" in _created_tables(db_url)
        assert _domain_fk_ondelete(db_url) == "CASCADE"

        command.downgrade(alembic_cfg, REVISION_BEFORE_CHUNKS)
        assert "agent_knowledge_chunks" not in _created_tables(db_url)
        assert _domain_fk_ondelete(db_url) is None

        command.upgrade(alembic_cfg, "head")
        assert "agent_knowledge_chunks" in _created_tables(db_url)
        assert _domain_fk_ondelete(db_url) == "CASCADE"


def test_the_entries_rebuild_keeps_the_rows_it_rebuilds(monkeypatch) -> None:
    """
    The SQLite path recreates agent_knowledge_entries to change its foreign
    key. A developer running this against dev.db has real content in that
    table, and a rebuild that quietly starts it empty would take the knowledge
    base with it.
    """
    with _alembic_on_a_temp_sqlite_db(monkeypatch) as (alembic_cfg, db_url):
        command.upgrade(alembic_cfg, REVISION_BEFORE_CHUNKS)

        engine = create_engine(db_url, poolclass=pool.NullPool)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO agent_domains (id, name, description, "
                    "group_visibility, sector_visibility, professional_domain, "
                    "is_active, created_at) VALUES ('d-1', 'zchuyot', 'desc', "
                    "'ALL', 'ALL', 'LAWYER', 1, '2026-09-01 10:00:00')"
                )
            )
            # updated_by points at no users row on purpose: SQLite does not
            # enforce foreign keys here, and spelling out every NOT NULL column
            # on users would tie this test to that table's shape instead of to
            # the one it is about.
            conn.execute(
                text(
                    "INSERT INTO agent_knowledge_entries (id, domain_id, title, "
                    "content, updated_by, created_at, updated_at) VALUES "
                    "('e-1', 'd-1', 'arnona', 'body', 'u-1', "
                    "'2026-09-01 10:00:00', '2026-09-01 10:00:00')"
                )
            )
        engine.dispose()

        command.upgrade(alembic_cfg, "head")
        assert _entry_ids(db_url) == {"e-1"}

        command.downgrade(alembic_cfg, REVISION_BEFORE_CHUNKS)
        assert _entry_ids(db_url) == {"e-1"}


# The revision ABF-156's meetings migration sits directly on top of.
REVISION_BEFORE_MEETINGS = "d4a1c7e93b52"


def _forum_post_columns(db_url: str) -> set[str]:
    engine = create_engine(db_url, poolclass=pool.NullPool)
    try:
        return {c["name"] for c in inspect(engine).get_columns("forum_posts")}
    finally:
        engine.dispose()  # release the file lock before tempdir cleanup (Windows)


def test_meetings_migration_goes_down_and_up_again_cleanly(monkeypatch) -> None:
    """
    ABF-156 adds two tables and two columns on an existing one, and the shared
    Definition of Done asks for a migration that runs both ways. The columns
    are what makes this worth asserting rather than assuming: dropping a column
    is the half of a downgrade SQLite is fussiest about, and a downgrade that
    leaves post_type behind makes the next upgrade fail with "duplicate column".
    """
    with _alembic_on_a_temp_sqlite_db(monkeypatch) as (alembic_cfg, db_url):
        command.upgrade(alembic_cfg, "head")
        assert {"meetings", "google_calendar_credentials"} <= _created_tables(db_url)
        assert {"post_type", "meeting_id"} <= _forum_post_columns(db_url)

        command.downgrade(alembic_cfg, REVISION_BEFORE_MEETINGS)
        assert not {"meetings", "google_calendar_credentials"} & _created_tables(db_url)
        assert not {"post_type", "meeting_id"} & _forum_post_columns(db_url)

        command.upgrade(alembic_cfg, "head")
        assert {"meetings", "google_calendar_credentials"} <= _created_tables(db_url)
        assert {"post_type", "meeting_id"} <= _forum_post_columns(db_url)


def test_existing_posts_are_backfilled_as_ordinary_posts(monkeypatch) -> None:
    """
    post_type is NOT NULL, and every post written before ABF-156 predates the
    column. The server_default is what answers for them — without it the
    migration cannot add the column at all on a database with posts in it, and
    a post that came back with no type would break the feed for everyone.
    """
    with _alembic_on_a_temp_sqlite_db(monkeypatch) as (alembic_cfg, db_url):
        command.upgrade(alembic_cfg, REVISION_BEFORE_MEETINGS)

        engine = create_engine(db_url, poolclass=pool.NullPool)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO forum_posts (id, author_id, group_visibility, "
                    "sector_visibility, title, content, status, report_count, "
                    "created_at, updated_at) VALUES ('p-1', 'u-1', 'WIDOWS', "
                    "'HASIDIC', 'כותרת', 'תוכן', 'VISIBLE', 0, "
                    "'2026-09-01 10:00:00', '2026-09-01 10:00:00')"
                )
            )
        engine.dispose()

        command.upgrade(alembic_cfg, "head")

        engine = create_engine(db_url, poolclass=pool.NullPool)
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT post_type, meeting_id FROM forum_posts WHERE id='p-1'")
                ).one()
        finally:
            engine.dispose()
        assert row[0] == "TEXT"
        assert row[1] is None


# The revision ABF-154's is_report_restricted column sits directly on top of.
REVISION_BEFORE_REPORT_RESTRICTED = "17e5d15f3029"


def _user_columns(db_url: str) -> set[str]:
    engine = create_engine(db_url, poolclass=pool.NullPool)
    try:
        return {c["name"] for c in inspect(engine).get_columns("users")}
    finally:
        engine.dispose()  # release the file lock before tempdir cleanup (Windows)


def _report_restricted_state(db_url: str) -> dict[str, object]:
    engine = create_engine(db_url, poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id, is_report_restricted FROM users")
            ).all()
    finally:
        engine.dispose()
    return {row[0]: row[1] for row in rows}


def test_report_restricted_migration_goes_down_and_up_again_cleanly(
    monkeypatch,
) -> None:
    """
    The shared Definition of Done asks for a migration that runs both ways
    (ABF-154, c5a90f47e2d1).

    The second upgrade is the point rather than a formality: a downgrade that
    leaves anything of the column behind fails on the way back up, which is
    where nobody is looking.
    """
    with _alembic_on_a_temp_sqlite_db(monkeypatch) as (alembic_cfg, db_url):
        command.upgrade(alembic_cfg, "head")
        assert "is_report_restricted" in _user_columns(db_url)

        # Named rather than "-1": this says which schema state the downgrade is
        # meant to land on, and it keeps saying it however the graph grows.
        command.downgrade(alembic_cfg, REVISION_BEFORE_REPORT_RESTRICTED)
        assert "is_report_restricted" not in _user_columns(db_url)

        command.upgrade(alembic_cfg, "head")
        assert "is_report_restricted" in _user_columns(db_url)


def test_report_restricted_backfills_existing_members_as_unrestricted(
    monkeypatch,
) -> None:
    """
    The column is NOT NULL and every deployed environment already has rows.
    Without the server_default the ALTER fails outright; with a nullable column
    instead, the rows would come out NULL — neither restricted nor
    unrestricted, and `if user.is_report_restricted` would read that as
    restricted and refuse a report from somebody who never filed a bad one.
    """
    with _alembic_on_a_temp_sqlite_db(monkeypatch) as (alembic_cfg, db_url):
        command.upgrade(alembic_cfg, REVISION_BEFORE_REPORT_RESTRICTED)

        engine = create_engine(db_url, poolclass=pool.NullPool)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, role, "
                    "first_name, last_name, account_status, is_active_professional, "
                    "is_suspended, created_at, updated_at) VALUES "
                    "('u-existing', 'member@example.com', 'hashed', 'USER', "
                    "'Test', 'User', 'ACTIVE', 1, 0, "
                    "'2026-09-01 10:00:00', '2026-09-01 10:00:00')"
                )
            )
        engine.dispose()

        command.upgrade(alembic_cfg, "head")

        assert _report_restricted_state(db_url) == {"u-existing": 0}
