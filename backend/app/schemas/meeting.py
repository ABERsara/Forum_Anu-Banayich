"""
Pydantic schemas for scheduled meetings and the calendar authorisation
that makes scheduling possible (ABF-156).
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from app.core.constants import GroupVisibility, SectorVisibility
from app.core.i18n import translate
from app.schemas.user import UserPublic


def _as_utc(value: datetime) -> datetime:
    """Name the zone of a timestamp read from the database: UTC.

    Every timestamp in this project is stored as naive UTC. Sent as it is,
    `2026-09-16T12:21:44` is read by `new Date(...)` and by Angular's date pipe
    as the *viewer's local* time — three hours off in Israel (see
    frontend/src/app/core/utils/utc-date.util.ts, written after the chat
    screen showed exactly that). Attached here, it goes out as `...Z`.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


#: An outgoing timestamp that states its zone. Output only — what a client
#: *sends* is AwareDatetime, which refuses a naive value instead of guessing.
#: Scoped to the meeting schemas on purpose: the rest of the API still sends
#: naive UTC, which the frontend compensates for with utcIso(), and utcIso()
#: passes a value that already has a zone through unchanged.
UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


def _future_naive_utc(value: datetime) -> datetime:
    """Normalise to naive UTC and refuse a meeting that already started.

    Always aware by the time it gets here — AwareDatetime has already refused
    anything else. Both halves belong in the schema rather than in the
    service: the "is it in the future" question is only meaningful once the
    zone has been resolved, and resolving it twice in two places is how the
    two answers drift apart. Shared by MeetingCreate and MeetingUpdate for the
    same reason.
    """
    value = value.astimezone(UTC).replace(tzinfo=None)
    if value <= datetime.now(UTC).replace(tzinfo=None):
        raise ValueError(translate("meetings.scheduled_in_past"))
    return value


class MeetingCreate(BaseModel):
    """POST /meetings – a professional schedules a meeting for one cell."""

    title: str = Field(..., min_length=2, max_length=256)

    #: When the meeting starts, with its zone stated — `...Z` or `+03:00`.
    #: A value without one is refused (422) rather than assumed to be UTC:
    #: an HTML datetime-local input sends the viewer's *local* wall-clock time
    #: with no zone, and reading that as UTC would book the meeting three
    #: hours late in Israel, silently. The client sends toISOString().
    #: Normalised to naive UTC by the validator below, which is how every
    #: timestamp in this project is stored.
    scheduled_at: AwareDatetime

    #: One cell: a concrete group and a concrete sector. "all" on either axis
    #: is rejected — a meeting is a support session for one group of people
    #: who share a situation, not a broadcast, and the announcement inherits
    #: exactly these two values.
    group_visibility: GroupVisibility
    sector_visibility: SectorVisibility

    @field_validator("scheduled_at")
    @classmethod
    def _future_utc(cls, value: datetime) -> datetime:
        return _future_naive_utc(value)

    @field_validator("group_visibility")
    @classmethod
    def _group_not_all(cls, value: GroupVisibility) -> GroupVisibility:
        if value == GroupVisibility.ALL:
            raise ValueError(translate("meetings.visibility_must_be_one_cell"))
        return value

    @field_validator("sector_visibility")
    @classmethod
    def _sector_not_all(cls, value: SectorVisibility) -> SectorVisibility:
        if value == SectorVisibility.ALL:
            raise ValueError(translate("meetings.visibility_must_be_one_cell"))
        return value


class MeetingUpdate(BaseModel):
    """PATCH /meetings/{id} – the creator changes the title, the time, or both.

    Each field is optional, and one that is left out is left as it is. The
    cell is not here on purpose: moving a meeting to another cell would move
    its announcement to members who never saw it and away from the ones who
    did, which is a new meeting, not an edit of this one. Neither is the
    duration, which ABF-156 fixes from the setting at creation.
    """

    title: str | None = Field(None, min_length=2, max_length=256)

    #: The same rules as MeetingCreate.scheduled_at: zone stated, in the
    #: future, stored as naive UTC.
    scheduled_at: AwareDatetime | None = None

    @field_validator("scheduled_at")
    @classmethod
    def _future_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _future_naive_utc(value)

    @model_validator(mode="after")
    def _something_to_change(self) -> "MeetingUpdate":
        """Refuse an empty body, and a field sent as an explicit null.

        Both would otherwise reach the service as "change nothing" or "set
        the title to None". The first is a request that cannot have meant
        anything, and the second would write NULL into a NOT NULL column and
        send Google an event without a summary.
        """
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError(translate("meetings.update_empty"))
        return self


class MeetingSummary(BaseModel):
    """
    The meeting as it travels on a forum post (ForumPostResponse.meeting).

    Everything a MEETING announcement needs to draw itself — when it starts,
    how long it runs, where to join — and nothing about who scheduled it,
    which the post already carries as its author.
    """

    id: str
    #: With its zone (`...Z`). The join button decides "is this meeting over"
    #: from this value, so a zone left for the client to guess is a button
    #: that switches off three hours early.
    scheduled_at: UtcDatetime
    duration_minutes: int
    meet_link: str

    model_config = {"from_attributes": True}


class MeetingResponse(BaseModel):
    """One meeting as returned by the meetings endpoints.

    Timestamps carry their zone, so a value read here can be sent back to
    POST /meetings as it is — which refuses the naive form.
    """

    id: str
    title: str
    scheduled_at: UtcDatetime
    duration_minutes: int
    meet_link: str
    group_visibility: GroupVisibility
    sector_visibility: SectorVisibility
    creator: UserPublic
    created_at: UtcDatetime

    model_config = {"from_attributes": True}


class CalendarConnectRequest(BaseModel):
    """
    POST /meetings/calendar/connect – what Google handed the return page.

    Both values are copied from the query string Google returned the browser
    with. Neither is trusted: the state is verified against the logged-in
    caller, and the code means nothing until Google accepts it.
    """

    code: str = Field(..., min_length=1, max_length=2048)
    state: str = Field(..., min_length=1, max_length=2048)


class CalendarStatusResponse(BaseModel):
    """
    GET /meetings/calendar/status – may this professional schedule yet?

    `authorization_url` travels with the answer instead of being a second
    endpoint: the scheduling form has to know both whether consent is needed
    and where to send her for it, and both are answers to the same question.
    It is always present, because a professional may also need to re-link a
    calendar whose access she revoked at Google or whose grant expired.
    """

    connected: bool
    connected_at: UtcDatetime | None = None
    authorization_url: str
