"""add the encrypted reported-message snapshot to reports, and make the
reporter id anonymizable

Revision ID: b8e41c9d7a35
Revises: a1ea93b2b792
Create Date: 2026-09-08 00:00:00.000000

Three changes, all of them the report-schema half of ABF-112. They travel in
one migration because they are one decision — the shape tasks 6, 7 and 8 of
this sprint build against, frozen early on purpose:

  * `reported_content` / `reported_content_key_version` — the reported private
    message, captured at report time and encrypted the same way the message
    itself is (app/core/encryption.py).
  * `reporter_id` becomes nullable, so §9.4's "reports are anonymized, not
    deleted, when an account closes" has somewhere to put the absence.
  * two enum members: `reportdecision.CLOSED_ACCOUNT_DELETED` and
    `auditaction.DIRECT_MESSAGE_REPORTED`.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e41c9d7a35"
down_revision: str | Sequence[str] | None = "a1ea93b2b792"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("reports") as batch_op:
        batch_op.add_column(sa.Column("reported_content", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("reported_content_key_version", sa.Integer(), nullable=True)
        )
        batch_op.alter_column(
            "reporter_id", existing_type=sa.String(length=36), nullable=True
        )

    # PostgreSQL: extend the two native enum types. PostgreSQL 12+ allows
    # `ALTER TYPE ... ADD VALUE` inside a transaction as long as the new value
    # is not *used* in the same transaction — nothing here writes either
    # member — so this stays atomic with the rest of the upgrade run. On
    # SQLite an enum column is plain VARCHAR with no CHECK, so there is
    # nothing to alter. Same shape as c73690be0286.
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TYPE reportdecision ADD VALUE IF NOT EXISTS 'CLOSED_ACCOUNT_DELETED'"
    )
    op.execute(
        "ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'DIRECT_MESSAGE_REPORTED'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Deliberately not backfilling the NOT NULL: a NULL reporter_id is an
    # anonymized report, and the only values that would satisfy the old
    # constraint are a real user's id (a false attribution) or a placeholder
    # row (a join target that re-correlates the reports anonymizing them was
    # meant to separate). So this fails loudly on a database that has already
    # anonymized something, rather than inventing a reporter or dropping the
    # report §9.4 says to keep for five years.
    with op.batch_alter_table("reports") as batch_op:
        batch_op.alter_column(
            "reporter_id", existing_type=sa.String(length=36), nullable=False
        )
        batch_op.drop_column("reported_content_key_version")
        batch_op.drop_column("reported_content")

    # PostgreSQL cannot remove a value from an enum type, so the two members
    # added above survive the downgrade. Harmless: an unused enum member
    # constrains nothing.
