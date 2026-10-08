"""
Meeting endpoints (ABF-156).

POST /meetings                     – schedule a meeting (professional only)
GET  /meetings                     – meetings still to come that you may see
GET  /meetings/calendar/status     – is this professional's calendar linked
POST /meetings/calendar/connect    – link the calendar Google just authorised
PATCH  /meetings/{meeting_id}      – change its title or time (its creator, ABF-163)
DELETE /meetings/{meeting_id}      – call it off (its creator, ABF-163)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.constants import UserRole
from app.core.dependencies import get_current_active_user, get_db, require_role
from app.models.user import User
from app.schemas.meeting import (
    CalendarConnectRequest,
    CalendarStatusResponse,
    MeetingCreate,
    MeetingResponse,
    MeetingUpdate,
)
from app.services import google_meet_service, meeting_service

router = APIRouter(tags=["Meetings"])


@router.post(
    "/meetings",
    response_model=MeetingResponse,
    status_code=201,
    dependencies=[Depends(require_role(UserRole.PROFESSIONAL))],
)
def create_meeting(
    data: MeetingCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> MeetingResponse:
    """
    Schedule a Google Meet for one cell and publish its announcement.

    A professional who has never linked her calendar, or whose grant was
    revoked or expired, gets a 403. So does a cell outside her assignment, and
    the detail is translated text rather than a key, so a client cannot tell
    these 403s apart from the response body. GET /meetings/calendar/status is
    the signal instead: the form asks it before submitting, and again after a
    403 — a revoked grant has been deleted by then, so it reports
    `connected: false`.
    """
    meeting = meeting_service.create_meeting(db, data, current_user)
    return MeetingResponse.model_validate(meeting)


@router.get("/meetings", response_model=list[MeetingResponse])
def list_meetings(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[MeetingResponse]:
    """
    Meetings that have not finished yet and are visible to the caller.

    Unpaginated, like GET /professionals: this is the handful of meetings
    ahead of one cell, not a growing archive — past meetings leave their
    announcement in the forum and drop out of here.
    """
    meetings = meeting_service.get_visible_meetings(db, current_user)
    return [MeetingResponse.model_validate(meeting) for meeting in meetings]


# The two calendar routes are declared before the /meetings/{meeting_id} ones
# for the usual FastAPI reason: routes match in order, and a path parameter
# declared first would swallow "calendar". No method is shared today, so
# nothing would actually collide — but the order is what keeps it that way
# when one is added.


@router.get(
    "/meetings/calendar/status",
    response_model=CalendarStatusResponse,
    dependencies=[Depends(require_role(UserRole.PROFESSIONAL))],
)
def calendar_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CalendarStatusResponse:
    """
    Whether this professional has authorised calendar access, and where to
    send her if she has not.
    """
    credential = google_meet_service.get_credential(db, current_user.id)
    return CalendarStatusResponse(
        connected=credential is not None,
        connected_at=credential.updated_at if credential else None,
        authorization_url=google_meet_service.build_authorization_url(current_user),
    )


@router.post(
    "/meetings/calendar/connect",
    response_model=CalendarStatusResponse,
    dependencies=[Depends(require_role(UserRole.PROFESSIONAL))],
)
def calendar_connect(
    data: CalendarConnectRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CalendarStatusResponse:
    """
    Link the calendar Google just authorised, for the logged-in professional.

    Google returns the browser to a page in the app (GOOGLE_REDIRECT_URI_MEET),
    which posts the `code` and `state` it arrived with here. Authenticated on
    purpose: the state must have been issued to this caller, which is what
    stops a consent link from being completed by anyone else — see
    google_meet_service._verify_state(). When she declines the consent screen
    Google returns `error=access_denied` instead of a code, and the page has
    nothing to post.

    Answers with the same body as GET /meetings/calendar/status, so the page
    can show the result without asking again.
    """
    credential = google_meet_service.exchange_calendar_token(
        db, data.code, data.state, current_user
    )
    return CalendarStatusResponse(
        connected=True,
        connected_at=credential.updated_at,
        authorization_url=google_meet_service.build_authorization_url(current_user),
    )


@router.patch(
    "/meetings/{meeting_id}",
    response_model=MeetingResponse,
    dependencies=[Depends(require_role(UserRole.PROFESSIONAL))],
)
def update_meeting(
    meeting_id: str,
    data: MeetingUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> MeetingResponse:
    """
    Change a meeting's title, its time, or both — its creator only.

    The meeting, its forum announcement and the event in her Google Calendar
    are updated together; the Meet link stays the same. 403 for every role but
    PROFESSIONAL and for a professional who did not create it, 404 for an
    unknown id, 409 once the meeting is cancelled or over, and 422 for an
    empty body, a null field, or a time that is not in the future. A failure
    at Google changes nothing here (502/504), and 403 is also what a revoked
    calendar grant answers, as on POST /meetings.
    """
    meeting = meeting_service.update_meeting(db, meeting_id, data, current_user)
    return MeetingResponse.model_validate(meeting)


@router.delete(
    "/meetings/{meeting_id}",
    status_code=204,
    dependencies=[Depends(require_role(UserRole.PROFESSIONAL))],
)
def cancel_meeting(
    meeting_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Call a meeting off — its creator only.

    Deletes the event from her Google Calendar and marks the announcement as
    cancelled. The announcement stays in the forum, reading "cancelled" with
    no join button, and the meeting drops out of GET /meetings. Nothing is
    hard-deleted. Idempotent: cancelling it again is a 204 that does nothing.
    The same 403/404 as PATCH, and 409 for a meeting that is already over —
    unless an earlier cancellation already deleted its event and failed to
    record it, which this one finishes (see meeting_service.cancel_meeting).
    """
    meeting_service.cancel_meeting(db, meeting_id, current_user)
