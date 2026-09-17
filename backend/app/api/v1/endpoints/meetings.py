"""
Meeting endpoints (ABF-156).

POST /meetings                     – schedule a meeting (professional only)
GET  /meetings                     – meetings still to come that you may see
GET  /meetings/calendar/status     – is this professional's calendar linked
POST /meetings/calendar/connect    – link the calendar Google just authorised
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


# The two calendar routes are declared before anything with a path parameter
# (there is none today) for the usual FastAPI reason: routes match in order,
# and a /meetings/{meeting_id} declared first would swallow "calendar".


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
