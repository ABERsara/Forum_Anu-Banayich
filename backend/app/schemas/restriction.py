"""
Pydantic schemas for the automatic restrictions of spec §7.2 (ABF-116).

Two audiences, two shapes, and they are not the same object with a field
hidden. What a restricted member is told about herself and what a moderator
is told about a member she oversees are different facts, and building the
member's view by dropping a field off the moderator's is how the extra field
comes back the next time someone adds one.
"""

from datetime import datetime

from pydantic import BaseModel

from app.core.constants import RestrictionType


class MyRestriction(BaseModel):
    """
    The restriction on the *current* user, as she is allowed to see it.

    Deliberately narrow. She is told what she cannot do and until when —
    everything a screen needs to explain itself and nothing more. No report
    count, no report id, no moderator: she is not owed the file, and a count
    of upheld reports handed back to the person they were filed against is a
    hint about who has been reporting her.
    """

    restriction_type: RestrictionType
    #: Naive UTC, like every timestamp this API returns — no offset and no
    #: trailing `Z`. A client has to say so before rendering it: both
    #: `new Date()` and Angular's date pipe read an offset-less string as
    #: *local* time, so read straight through, this field names a time three
    #: hours before the restriction actually ends in Israel. The Angular
    #: client passes it through `core/utils/utc-date.util.ts` first.
    expires_at: datetime


class MyRestrictionResponse(BaseModel):
    """
    GET /messages/restriction — always 200, with `restriction` null when
    there is none.

    Null rather than 404: "you are not restricted" is a successful answer to
    a question every chat screen asks on open, and a 404 would put a red line
    in the console of every member who is fine.
    """

    restriction: MyRestriction | None = None


class RestrictedMember(BaseModel):
    """The member a restriction applies to, as a moderator dashboard shows her."""

    id: str
    first_name: str
    last_name: str

    model_config = {"from_attributes": True}


class RestrictionWithMember(BaseModel):
    """
    One active restriction in a moderator's cells (§7.3).

    Carries the evidence — how many decided reports, over what window — so
    the dashboard can say *why* the platform did this without the moderator
    having to reconstruct it from the report queue. Still no report content
    and no reporter: §5.3 gives her one reported message at a time, through
    the report it was handed over with, not through a list of restrictions.
    """

    id: str
    restriction_type: RestrictionType
    expires_at: datetime
    report_count: int
    window_days: int
    created_at: datetime
    member: RestrictedMember


class RestrictionListResponse(BaseModel):
    """
    GET /moderator/restrictions.

    Unpaginated, like the pending-reports queue beside it and for the same
    reason: it is a list of what is in force right now, it shrinks by itself
    as restrictions expire, and a moderator's cells cannot hold enough
    simultaneously restricted members for a page to be needed.
    """

    items: list[RestrictionWithMember]
    total: int
