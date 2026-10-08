"""add report_restriction_lifted_at to users

Revision ID: 953f562dc226
Revises: 2d0766bdb16c
Create Date: 2026-10-08 00:00:00.000000

ABF-XXX. When an admin last lifted `is_report_restricted` by hand (ABF-162).
report_service._check_frequent_false_reporter() counts only the dismissals
decided after it, so a lift is not undone by the next dismissal of a report
that was already waiting in the queue.

Nullable, no default: NULL is "never lifted", and the rule reads it as the
30-day window alone, which is how every member is counted today.

Backfilled from the lift's own audit entry, so a member an admin lifted
between ABF-162's merge and this deploy gets the clean slate too. Without it
her column would come out NULL and the next dismissal could restrict her
again on the very count that was lifted. The entry's `timestamp` is the
database's naive `now()`, the same UTC convention `created_at` follows
(restriction_service._now() relies on it too). The latest lift per member
wins, as it does at runtime.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "953f562dc226"
down_revision: str | Sequence[str] | None = "2d0766bdb16c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# What user_service.lift_report_restriction() writes in `details`.
LIFT_MEASURE = "report_restriction_lifted"

# Lightweight table handles for the backfill, as in 3a7c1f9b2d64: SQLAlchemy
# expressions rather than literal SQL, so the same statement runs on SQLite
# and PostgreSQL.
audit_logs = sa.table(
    "audit_logs",
    sa.column("action", sa.String),
    sa.column("entity_type", sa.String),
    sa.column("entity_id", sa.String),
    sa.column("details", sa.JSON),
    sa.column("timestamp", sa.DateTime),
)
users = sa.table(
    "users",
    sa.column("id", sa.String),
    sa.column("report_restriction_lifted_at", sa.DateTime),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("report_restriction_lifted_at", sa.DateTime(), nullable=True),
    )

    # `action` is cast because on PostgreSQL it is the `auditaction` enum,
    # which has no `=` against a varchar parameter; the enum stores the
    # member's name. `measure` is matched here rather than in SQL: JSON
    # operators differ between the two dialects, and USER_RESTRICTED entries
    # about a User are a handful per member, not a scan of the log.
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(audit_logs.c.entity_id, audit_logs.c.details, audit_logs.c.timestamp)
        .where(sa.cast(audit_logs.c.action, sa.String) == "USER_RESTRICTED")
        .where(audit_logs.c.entity_type == "User")
    )
    latest: dict[str, datetime] = {}
    for entity_id, details, timestamp in rows:
        if (details or {}).get("measure") != LIFT_MEASURE:
            continue
        if entity_id not in latest or timestamp > latest[entity_id]:
            latest[entity_id] = timestamp

    for user_id, lifted_at in latest.items():
        op.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(report_restriction_lifted_at=lifted_at)
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "report_restriction_lifted_at")
