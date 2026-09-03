"""add agent tables

Revision ID: 79daa6708dd8
Revises: aac7e1fb8f49
Create Date: 2026-08-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "79daa6708dd8"
down_revision: str | Sequence[str] | None = "aac7e1fb8f49"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_domains",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        # group/sector/professional_domain reuse enum types created in the
        # initial migration. postgresql.ENUM(..., create_type=False) is required:
        # on generic sa.Enum the create_type kwarg is silently ignored, so an
        # incremental `alembic upgrade` on an existing Postgres DB would emit a
        # second CREATE TYPE and fail with DuplicateObject. On SQLite these
        # render as VARCHAR exactly as a plain sa.Enum would.
        sa.Column(
            "group_visibility",
            postgresql.ENUM(
                "WIDOWERS",
                "WIDOWS",
                "ORPHANS_MALE",
                "ORPHANS_FEMALE",
                "ALL",
                name="groupvisibility",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "sector_visibility",
            postgresql.ENUM(
                "HASIDIC",
                "LITVISH",
                "SEPHARDIC",
                "GENERAL",
                "ALL",
                name="sectorvisibility",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "professional_domain",
            postgresql.ENUM(
                "LAWYER",
                "ACCOUNTANT",
                "PSYCHOLOGIST",
                "FINANCIAL_ADVISOR",
                "RABBI",
                "MEDICINE",
                "SOCIAL_WORKER",
                "OTHER",
                name="professionaldomain",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_knowledge_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("domain_id", sa.String(length=36), nullable=False),
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
        sa.ForeignKeyConstraint(["domain_id"], ["agent_domains.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_knowledge_entries_domain_id",
        "agent_knowledge_entries",
        ["domain_id"],
    )
    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("domain_id", sa.String(length=36), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "last_message_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["domain_id"], ["agent_domains.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_conversations_domain_id",
        "agent_conversations",
        ["domain_id"],
    )
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column(
            "role",
            sa.Enum("USER", "AGENT", name="agentmessagerole"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_messages_conversation_id",
        "agent_messages",
        ["conversation_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_agent_messages_conversation_id", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index("ix_agent_conversations_domain_id", table_name="agent_conversations")
    op.drop_table("agent_conversations")
    op.drop_index(
        "ix_agent_knowledge_entries_domain_id",
        table_name="agent_knowledge_entries",
    )
    op.drop_table("agent_knowledge_entries")
    op.drop_table("agent_domains")
    # agentmessagerole is created by this migration, so this migration drops it
    # (no-op on SQLite). The visibility/professional_domain enums are shared with
    # other tables and are deliberately left in place.
    sa.Enum("USER", "AGENT", name="agentmessagerole").drop(
        op.get_bind(), checkfirst=True
    )
