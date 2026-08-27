"""add google_uid to users

Revision ID: 4fbb595f14de
Revises: 9dd5b3c88c0d
Create Date: 2026-08-19 11:50:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4fbb595f14de"
down_revision: Union[str, Sequence[str], None] = "9dd5b3c88c0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # batch mode: SQLite can't ALTER TABLE to add a constraint directly, it
    # has to recreate the table — batch_alter_table handles that for us and
    # is a no-op wrapper (plain ALTER TABLE) on PostgreSQL.
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("google_uid", sa.String(length=128), nullable=True))
        batch_op.create_unique_constraint("uq_users_google_uid", ["google_uid"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_google_uid", type_="unique")
        batch_op.drop_column("google_uid")
