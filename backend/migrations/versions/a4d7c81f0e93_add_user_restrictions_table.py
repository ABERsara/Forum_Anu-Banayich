"""add user_restrictions table and USER_RESTRICTED audit action

Revision ID: a4d7c81f0e93
Revises: 45019c151eb8
Create Date: 2026-09-10 00:00:00.000000

ABF-116 — spec §5.3's מה"ק and §7.2's two automatic thresholds.

Two changes in one revision because they are one change: a restriction that
is applied without an audit entry naming it is the thing §9.3 exists to
prevent, so the table and the `auditaction` value that records writing to it
have to arrive together. `tests/test_migration_enum_consistency.py` unions
every contribution to a DB enum across the whole history, so an
`ALTER TYPE ... ADD VALUE` here satisfies it without the initial migration
being touched (CONTRIBUTING §2 — a shipped migration is never edited).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4d7c81f0e93"
down_revision: str | Sequence[str] | None = "45019c151eb8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESTRICTIONS_INDEX = "ix_user_restrictions_user_type_expires"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_restrictions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "restriction_type",
            sa.Enum("MESSAGING", "REPORTING", name="restrictiontype"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("report_count", sa.Integer(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("triggered_by_report_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["triggered_by_report_id"], ["reports.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # The one query the private-message send path runs before every send:
    # "is there a live restriction of this kind for this member".
    op.create_index(
        RESTRICTIONS_INDEX,
        "user_restrictions",
        ["user_id", "restriction_type", "expires_at"],
    )

    # PostgreSQL: extend the native `auditaction` enum type. PostgreSQL 12+
    # allows `ALTER TYPE ... ADD VALUE` inside a transaction as long as the new
    # value is not *used* in the same transaction (it is not here), so this runs
    # in the migration's own transaction and stays atomic with the table above.
    # IF NOT EXISTS keeps it idempotent on re-run. On SQLite the enum column is
    # plain VARCHAR with no CHECK, so there is nothing to alter.
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'USER_RESTRICTED'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(RESTRICTIONS_INDEX, table_name="user_restrictions")
    op.drop_table("user_restrictions")

    # PostgreSQL keeps an enum type after the last table using it is dropped,
    # so dropping it here is what makes the downgrade actually clean — without
    # it, upgrading again fails on "type restrictiontype already exists".
    # SQLite has no type to drop.
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TYPE IF EXISTS restrictiontype")
    # `auditaction` keeps USER_RESTRICTED: PostgreSQL cannot remove a value
    # from an enum type, and the audit rows that used it are append-only and
    # kept for seven years (§9.3) — they outlive this table by design.
