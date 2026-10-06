"""add filter/sort indexes to audit_logs

Revision ID: a80e87afe0fa
Revises: e7b3f19c4a06
Create Date: 2026-10-06 00:00:00.000000

ABF-152 — GET /admin/audit-log filters on actor_id, action, entity_type and
entity_id, and sorts on timestamp. LIMIT/OFFSET bounds what comes back, not
what is read: without an index the database scans the whole table to find the
matching rows before it can cut a page out of them, and audit_logs is
append-only with a seven-year retention.

One index per column rather than a composite: the contract lets any subset
of the filters be combined, and a composite only serves queries that use its
leading column.

The column is `action`, not `action_type` — `action_type` is the name of the
API parameter, `action` is the name of the column (models/audit.py).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a80e87afe0fa"
down_revision: str | Sequence[str] | None = "e7b3f19c4a06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The names SQLAlchemy gives `index=True` on models/audit.py, so the model and
# this migration describe the same indexes and autogenerate sees no drift.
INDEXED_COLUMNS = ("actor_id", "action", "entity_type", "entity_id", "timestamp")


def upgrade() -> None:
    """Upgrade schema."""
    for column in INDEXED_COLUMNS:
        op.create_index(f"ix_audit_logs_{column}", "audit_logs", [column])


def downgrade() -> None:
    """Downgrade schema."""
    for column in reversed(INDEXED_COLUMNS):
        op.drop_index(f"ix_audit_logs_{column}", table_name="audit_logs")
