"""merge read-at and agent-conversation heads

Revision ID: d3f0a6b71c58
Revises: 3a7c1f9b2d64, b7a1c4d92f30
Create Date: 2026-09-06 00:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d3f0a6b71c58"
down_revision: str | Sequence[str] | None = ("3a7c1f9b2d64", "b7a1c4d92f30")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
