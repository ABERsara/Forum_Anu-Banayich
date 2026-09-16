"""
Scheduled Google Meet meeting (ABF-156).

A professional schedules a meeting for one cell — one group AND one sector,
never "all" on either axis — and the system publishes the announcement as a
ForumPost of type MEETING. There is no email: the forum announcement is the
notification, so nobody is added to the Google event as an attendee (see
google_meet_service.create_meeting()).

Separate from ForumPost on purpose. The post is the announcement, which is
moderated, listed and paged like any other post; this row is the meeting
itself — the thing that exists on Google's side and that a join button acts
on. One table doing both would mean every forum query carrying columns that
are null for all but a handful of rows.

The row outlives its announcement, but it is not *published* without it:
when moderation deletes or hides the announcement, GET /meetings stops
listing the meeting (see meeting_service.get_visible_meetings()). The row
and the Google event remain — cancelling a meeting is outside ABF-156.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import GroupVisibility, SectorVisibility
from app.db.base import Base


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    #: The professional who scheduled it. The event lives in *her* Google
    #: Calendar — see google_calendar_credential.py — so this is both the
    #: author of the announcement and the owner of the external event.
    creator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(256), nullable=False)

    #: Naive UTC, like every other timestamp in this project (see
    #: DirectMessage.created_at). Converted to an RFC 3339 "...Z" instant on
    #: the way to Google, and rendered in the viewer's own zone by the client.
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    #: How long the meeting was actually booked for. Defaulted from
    #: settings.MEETING_DEFAULT_DURATION_MINUTES at creation time and then
    #: frozen here, rather than read back from the setting: the Google event
    #: is fixed the moment it is created, so a later change to the default
    #: must not retroactively move the moment an old meeting counts as over.
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    #: The Meet URL members join. Google's, not ours — we never mint it.
    meet_link: Mapped[str] = mapped_column(String(1024), nullable=False)
    #: The Calendar event id, kept so a future ticket can cancel or edit the
    #: meeting (both explicitly out of scope for ABF-156) without having to
    #: search the professional's calendar for it.
    calendar_event_id: Mapped[str] = mapped_column(String(256), nullable=False)

    # ------------------------------------------------------------------
    # Visibility — the same two axes as ForumPost, and the announcement post
    # is created with exactly these values. Both are concrete: a meeting
    # belongs to one cell (group+sector), so GroupVisibility.ALL /
    # SectorVisibility.ALL are rejected by meeting_service, not stored here.
    # ------------------------------------------------------------------
    group_visibility: Mapped[GroupVisibility] = mapped_column(
        Enum(GroupVisibility), nullable=False
    )
    sector_visibility: Mapped[SectorVisibility] = mapped_column(
        Enum(SectorVisibility), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    creator: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", foreign_keys=[creator_id]
    )
    #: The announcement. A list rather than a scalar because the foreign key
    #: lives on ForumPost (that is the direction the forum feed reads it in),
    #: and exactly one is ever created — see meeting_service.create_meeting().
    posts: Mapped[list["ForumPost"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ForumPost", back_populates="meeting", foreign_keys="ForumPost.meeting_id"
    )

    def __repr__(self) -> str:
        return f"<Meeting id={self.id} scheduled_at={self.scheduled_at}>"
