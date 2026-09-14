"""add agent knowledge chunks

Revision ID: d4a1c7e93b52
Revises: a4d7c81f0e93
Create Date: 2026-09-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "d4a1c7e93b52"
down_revision: str | Sequence[str] | None = "a4d7c81f0e93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept literal here rather than imported from app.models.agent: a shipped
# migration describes the schema as it was on the day it ran, and must not
# start building a different table because a model constant changed later.
EMBEDDING_DIMENSIONS = 768

# VECTOR is a PostgreSQL type. On SQLite the column is TEXT — see the same
# variant on AgentKnowledgeChunk.embedding for why the two dialects have to
# agree on this.
EMBEDDING_TYPE = Vector(EMBEDDING_DIMENSIONS).with_variant(sa.Text(), "sqlite")

# Revision 79daa6708dd8 created agent_knowledge_entries.domain_id with a plain
# FK, so deleting a domain errored on the entries pointing at it instead of
# taking them with it. Fixed here rather than by editing that migration.
_ENTRIES_TABLE = "agent_knowledge_entries"
_DOMAIN_FK_COLUMN = "domain_id"


def _entries_table(*, cascade: bool) -> sa.Table:
    """agent_knowledge_entries as revision 79daa6708dd8 built it, either FK.

    SQLite cannot alter a constraint; the only way to change one is to rebuild
    the table around it, and a rebuild needs the full definition of what to
    rebuild. Spelled out here rather than reflected, so the rebuilt table is
    what this migration says it is on any database it meets — and spelled out
    again rather than imported from the model, for the same reason the column
    widths below are literal: a shipped migration must not change shape because
    a model changed later.
    """
    return sa.Table(
        _ENTRIES_TABLE,
        sa.MetaData(),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(_DOMAIN_FK_COLUMN, sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(length=256), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            [_DOMAIN_FK_COLUMN],
            ["agent_domains.id"],
            ondelete="CASCADE" if cascade else None,
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_agent_knowledge_entries_domain_id", _DOMAIN_FK_COLUMN),
    )


def _rebuild_entries_with(*, cascade: bool) -> None:
    """Recreate agent_knowledge_entries on SQLite with the FK set either way.

    Alembic copies the rows across as part of the batch rebuild, so this is
    lossless for a developer's dev.db as well as for a fresh test database.
    """
    with op.batch_alter_table(
        _ENTRIES_TABLE,
        copy_from=_entries_table(cascade=cascade),
        recreate="always",
    ):
        pass


def _domain_fk_name() -> str:
    """The real name PostgreSQL gave the entries→domains FK.

    Read off the database rather than assumed to be the
    `<table>_<column>_fkey` default: a database restored from a dump, or
    created before a rename, can carry a different one, and dropping a
    constraint by a guessed name fails the whole upgrade.
    """
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(_ENTRIES_TABLE):
        if fk["constrained_columns"] == [_DOMAIN_FK_COLUMN]:
            name = fk["name"]
            if name:
                return str(name)
    raise RuntimeError(
        f"No named foreign key on {_ENTRIES_TABLE}.{_DOMAIN_FK_COLUMN} — "
        "cannot rebuild it with ON DELETE CASCADE."
    )


def upgrade() -> None:
    """Upgrade schema."""
    is_postgresql = op.get_bind().dialect.name == "postgresql"

    if is_postgresql:
        # Makes the vector type available in this database. The image only
        # ships the extension; nothing exists until it is created here.
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # The inherited FK gap, closed on both dialects — PostgreSQL can alter the
    # constraint in place, SQLite has to rebuild the table around it. Doing it
    # on PostgreSQL alone would leave the dev and test databases describing a
    # schema production does not have, which is exactly the drift
    # test_no_agent_model_migration_drift exists to catch.
    #
    # Before agent_knowledge_chunks exists, deliberately: SQLite's rebuild
    # renames the table it is rebuilding, and a rename rewrites the references
    # to it in other tables' foreign keys — which would leave the chunks table
    # pointing at a temporary name that is about to be dropped.
    if is_postgresql:
        op.drop_constraint(_domain_fk_name(), _ENTRIES_TABLE, type_="foreignkey")
        op.create_foreign_key(
            "agent_knowledge_entries_domain_id_fkey",
            _ENTRIES_TABLE,
            "agent_domains",
            [_DOMAIN_FK_COLUMN],
            ["id"],
            ondelete="CASCADE",
        )
    else:
        _rebuild_entries_with(cascade=True)

    op.create_table(
        "agent_knowledge_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entry_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("embedding", EMBEDDING_TYPE, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["agent_knowledge_entries.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        # Re-indexing rebuilds an entry's chunks from scratch, so index 0..n-1
        # is written fresh every time; the constraint is what says a stale
        # duplicate never survives alongside them.
        sa.UniqueConstraint(
            "entry_id", "chunk_index", name="uq_agent_knowledge_chunks_entry_index"
        ),
    )
    op.create_index(
        "ix_agent_knowledge_chunks_entry_id",
        "agent_knowledge_chunks",
        ["entry_id"],
    )

    # No ivfflat/hnsw index: retrieval is an exact scan over one domain's
    # chunks, which is the right trade at this size (an approximate index costs
    # recall and has to be rebuilt as rows arrive). Adding one later is a
    # migration of its own and needs no application change.


def downgrade() -> None:
    """Downgrade schema."""
    is_postgresql = op.get_bind().dialect.name == "postgresql"

    # Mirror image of upgrade(): the chunks table goes first, so the SQLite
    # rebuild below has no table referencing the one it recreates.
    op.drop_index(
        "ix_agent_knowledge_chunks_entry_id", table_name="agent_knowledge_chunks"
    )
    op.drop_table("agent_knowledge_chunks")

    if is_postgresql:
        op.drop_constraint(_domain_fk_name(), _ENTRIES_TABLE, type_="foreignkey")
        op.create_foreign_key(
            "agent_knowledge_entries_domain_id_fkey",
            _ENTRIES_TABLE,
            "agent_domains",
            [_DOMAIN_FK_COLUMN],
            ["id"],
        )
    else:
        _rebuild_entries_with(cascade=False)

    # The vector extension is deliberately left in place: other databases in
    # the same cluster may rely on it, and DROP EXTENSION would take their
    # columns with it.
