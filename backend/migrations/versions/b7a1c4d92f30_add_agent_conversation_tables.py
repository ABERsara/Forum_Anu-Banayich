"""add agent conversation and knowledge base tables

Revision ID: b7a1c4d92f30
Revises: aac7e1fb8f49
Create Date: 2026-09-03 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b7a1c4d92f30"
down_revision: str | Sequence[str] | None = "aac7e1fb8f49"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------
# Enum types
#
# On PostgreSQL an enum is a schema object with a life of its own: it outlives
# a DROP TABLE, and a second CREATE TYPE of the same name is an error. Two of
# the tables below share `agentdomain`, so both types are created once here,
# up front, and every column references them without re-creating them (see
# _enum_column). On SQLite none of this applies — an enum column is a VARCHAR
# with no constraint, and .create()/.drop() are no-ops.
#
# These two definitions are also what test_migration_enum_consistency reads to
# check the migration against app/core/constants.py, so their member lists
# must stay complete.
# ---------------------------------------------------------------------------

AGENT_DOMAIN = sa.Enum("SINGLE_PARENT_RIGHTS", name="agentdomain")
AGENT_MESSAGE_ROLE = sa.Enum("USER", "AGENT", name="agentmessagerole")


def _enum_column(enum_type: sa.Enum) -> sa.types.TypeEngine[str]:
    """Reference an already-created enum type from a column definition."""
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM(*enum_type.enums, name=enum_type.name, create_type=False)
    return enum_type


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    AGENT_DOMAIN.create(bind, checkfirst=True)
    AGENT_MESSAGE_ROLE.create(bind, checkfirst=True)

    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("domain", _enum_column(AGENT_DOMAIN), nullable=False),
        # Written from Python in naive UTC rather than by the DB clock — see
        # the _utc_now() docstring in app/models/agent.py for why a chat needs
        # sub-second timestamps.
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_conversations_user_created",
        "agent_conversations",
        ["user_id", "created_at"],
    )

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", _enum_column(AGENT_MESSAGE_ROLE), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_messages_conversation_created",
        "agent_messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "agent_knowledge_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("domain", _enum_column(AGENT_DOMAIN), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_knowledge_chunks_domain", "agent_knowledge_chunks", ["domain"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_agent_knowledge_chunks_domain", table_name="agent_knowledge_chunks"
    )
    op.drop_table("agent_knowledge_chunks")
    op.drop_index("ix_agent_messages_conversation_created", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index(
        "ix_agent_conversations_user_created", table_name="agent_conversations"
    )
    op.drop_table("agent_conversations")

    # DROP TABLE leaves the types behind on PostgreSQL, and a re-run of
    # upgrade() would then fail on CREATE TYPE.
    bind = op.get_bind()
    AGENT_MESSAGE_ROLE.drop(bind, checkfirst=True)
    AGENT_DOMAIN.drop(bind, checkfirst=True)
