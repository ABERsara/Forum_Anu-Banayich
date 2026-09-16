"""
Meeting endpoints (ABF-156).

POST /meetings                     – schedule a meeting (professional only)
GET  /meetings                     – meetings still to come that you may see
GET  /meetings/calendar/status     – is this professional's calendar linked
GET  /meetings/calendar/callback   – where Google returns after consent
"""

import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import UserRole
from app.core.dependencies import get_current_active_user, get_db, require_role
from app.models.user import User
from app.schemas.meeting import CalendarStatusResponse, MeetingCreate, MeetingResponse
from app.services import google_meet_service, meeting_service

logger = logging.getLogger(__name__)

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


@router.get("/meetings/calendar/callback", include_in_schema=False)
def calendar_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Where Google returns the browser after the consent screen.

    No authentication dependency, and there cannot be one: this is a
    navigation Google triggers, with no Authorization header to read. The
    signed `state` issued by /meetings/calendar/status is what identifies the
    professional — see google_meet_service._user_from_state().

    Every outcome ends as a redirect back into the app with the result in the
    query string, because what arrives here is a browser, not a client that
    can read a JSON error body. The detail of a failure is logged rather than
    put in the URL: query strings end up in history and access logs.
    """
    outcome = "connected"
    if error or not code or not state:
        # Google sends ?error=access_denied when she declines the consent
        # screen. Declining is a choice, not a fault — it is reported
        # separately from a failure so the app can say so.
        outcome = "denied" if error == "access_denied" else "error"
    else:
        try:
            google_meet_service.exchange_calendar_token(db, code, state)
        except Exception:
            logger.exception("Calendar authorisation failed at the callback")
            outcome = "error"

    return RedirectResponse(
        f"{settings.GOOGLE_CALENDAR_RETURN_URL}?calendar={outcome}", status_code=302
    )
