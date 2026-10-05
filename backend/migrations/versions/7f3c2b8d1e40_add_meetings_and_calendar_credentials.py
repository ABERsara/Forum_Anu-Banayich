"""add meetings, google calendar credentials, and forum post type

Revision ID: 7f3c2b8d1e40
Revises: d4a1c7e93b52
Create Date: 2026-09-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7f3c2b8d1e40"
down_revision: str | Sequence[str] | None = "d4a1c7e93b52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The one enum type ABF-156 introduces. Declared once here so the explicit
# CREATE TYPE below and the column that uses it cannot drift apart.
#
# create_type=False on the column, plus an explicit .create(): op.add_column()
# does NOT emit CREATE TYPE for a new enum on PostgreSQL (it only does so
# inside create_table), so a column declared with a plain sa.Enum would fail
# with "type posttype does not exist" on the deployed database while passing
# on SQLite, where every enum is just a VARCHAR.
_POST_TYPE = postgresql.ENUM("TEXT", "MEETING", name="posttype", create_type=False)

# Reused types, created by the initial migration. See 79daa6708dd8 for why
# these are postgresql.ENUM(create_type=False) and not sa.Enum.
_GROUP_VISIBILITY = postgresql.ENUM(
    "WIDOWERS",
    "WIDOWS",
    "ORPHANS_MALE",
    "ORPHANS_FEMALE",
    "ALL",
    name="groupvisibility",
    create_type=False,
)
_SECTOR_VISIBILITY = postgresql.ENUM(
    "HASIDIC",
    "LITVISH",
    "SEPHARDIC",
    "GENERAL",
    "ALL",
    name="sectorvisibility",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _POST_TYPE.create(bind, checkfirst=True)

    op.create_table(
        "meetings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("creator_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("meet_link", sa.String(length=1024), nullable=False),
        sa.Column("calendar_event_id", sa.String(length=256), nullable=False),
        sa.Column("group_visibility", _GROUP_VISIBILITY, nullable=False),
        sa.Column("sector_visibility", _SECTOR_VISIBILITY, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "google_calendar_credentials",
        # The user id is the primary key: one authorisation per professional,
        # and re-authorising replaces it rather than adding a second row.
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=512), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # server_default backfills every post that already exists — the column is
    # NOT NULL, and there is no other way to answer what type a post written
    # before ABF-156 is. It stays on the column afterwards: a plain INSERT
    # from a script or a future migration then still lands on TEXT rather
    # than failing, and the model writes the same value explicitly.
    op.add_column(
        "forum_posts",
        sa.Column("post_type", _POST_TYPE, nullable=False, server_default="TEXT"),
    )
    op.add_column(
        "forum_posts", sa.Column("meeting_id", sa.String(length=36), nullable=True)
    )
    if bind.dialect.name != "sqlite":
        # The foreign key is added as a separate constraint, and only off
        # SQLite: SQLite cannot ALTER a constraint onto an existing table at
        # all ("No support for ALTER of constraints"), and the way round it —
        # batch mode — copies the whole forum_posts table to add a constraint
        # that SQLite does not enforce by default anyway. PostgreSQL, which is
        # what production runs and what would actually enforce it, gets it.
        op.create_foreign_key(
            "fk_forum_posts_meeting_id_meetings",
            "forum_posts",
            "meetings",
            ["meeting_id"],
            ["id"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        # Dropped explicitly rather than left to the column drop: PostgreSQL
        # would take it with the column, but naming it here keeps the
        # downgrade symmetric with the upgrade that created it.
        op.drop_constraint(
            "fk_forum_posts_meeting_id_meetings", "forum_posts", type_="foreignkey"
        )
    op.drop_column("forum_posts", "meeting_id")
    op.drop_column("forum_posts", "post_type")
    op.drop_table("google_calendar_credentials")
    op.drop_table("meetings")

    if bind.dialect.name == "postgresql":
        # Dropped only after the column that used it is gone, and only on
        # PostgreSQL — on SQLite the type never existed as an object.
        _POST_TYPE.drop(bind, checkfirst=True)
