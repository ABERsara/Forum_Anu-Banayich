"""
Google Calendar / Meet boundary (ABF-156).

Everything in this module is I/O with Google and the storage of the
authorisation that makes it possible. The rules about *who* may schedule a
meeting for *which* cell, and what the platform writes down when one is
scheduled, live in meeting_service.py — this file would happily create an
event for anyone who asked.

Plain httpx against the REST API rather than google-api-python-client: the
project already talks to a Google API this way (rag_service.py), the surface
used here is three endpoints, and the client library would pull in a
dependency tree — and its own credential/refresh machinery — for no gain.

Why an OAuth authorisation-code flow at all, when auth_service already does
"log in with Google": that one verifies a Firebase ID token, which proves
identity and grants nothing. Creating an event in someone's calendar is an
authorisation, with its own consent screen and its own refresh token.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import decrypt_message, encrypt_message
from app.core.i18n import translate
from app.core.security import ALGORITHM
from app.models.google_calendar_credential import GoogleCalendarCredential
from app.models.user import User

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_EVENTS_URL = (
    "https://www.googleapis.com/calendar/v3/calendars/primary/events"
)

#: How long the `state` handed to Google stays valid. Long enough to read a
#: consent screen, short enough that a link left in a browser's history is
#: not an open invitation to attach a calendar to someone else's account.
STATE_EXPIRE_MINUTES = 15

#: Marks our own state tokens, so an access token pasted into the callback is
#: rejected rather than accepted as a state (and vice versa — decode_access_token
#: applies the same check in the other direction).
STATE_TOKEN_TYPE = "calendar_state"


def _require_configuration() -> None:
    """Fail with the missing setting named, before any call to Google.

    An unconfigured deployment reaches Google with client_id="" and gets back
    an OAuth error page, or a 401 whose body says "invalid_client" — neither
    of which tells the person reading the logs which environment variable to
    set. Checked at the point of use rather than at startup on purpose: the
    rest of the API works without this integration (see config.py).
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=503, detail=translate("meetings.calendar_not_configured")
        )


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


def _create_state(user: User) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=STATE_EXPIRE_MINUTES)
    payload = {"sub": user.id, "exp": expire, "type": STATE_TOKEN_TYPE}
    return str(jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM))


def _verify_state(state: str, user: User) -> None:
    """Refuse a state that was not issued to the professional presenting it.

    Two checks, and the second is the one that matters. The signature proves
    we issued the state, so nobody can attach their own calendar to another
    account. The subject has to equal the logged-in caller as well: otherwise
    a professional could send her authorization_url to someone else, and if
    that person approved it, *their* calendar would be stored against *her*
    account — and every meeting she scheduled created in it. With the check,
    that person's browser presents her state under their own login and is
    refused, and the code Google gave them is never exchanged.

    This is why Google returns the browser to a frontend route that posts
    code+state with the user's JWT, rather than to an API callback: a
    navigation carries no Authorization header, so an API callback has no
    caller to compare against. A nonce in a cookie would do the same job, but
    the frontend and the API are on different domains, and a cookie set from a
    cross-site request is exactly what browsers increasingly block.

    A mismatch gets the same answer as a forged or expired state, so the
    response says nothing about whose link it was.
    """
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != STATE_TOKEN_TYPE:
            raise JWTError("not a calendar state token")
        if payload.get("sub") != user.id:
            raise JWTError("issued to another user")
    except JWTError:
        raise HTTPException(
            status_code=400, detail=translate("meetings.calendar_state_invalid")
        ) from None


def build_authorization_url(user: User) -> str:
    """The Google consent URL this professional should be sent to."""
    _require_configuration()
    query = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI_MEET,
        "response_type": "code",
        "scope": settings.GOOGLE_CALENDAR_SCOPE,
        # Without access_type=offline Google returns an access token and no
        # refresh token, and the authorisation would silently stop working an
        # hour later.
        "access_type": "offline",
        # And without prompt=consent it omits the refresh token on every
        # authorisation after the first — so a professional re-authorising
        # after her grant was revoked or expired would get a row we cannot
        # refresh.
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": _create_state(user),
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(query)}"


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def get_credential(db: Session, user_id: str) -> GoogleCalendarCredential | None:
    return (
        db.query(GoogleCalendarCredential)
        .filter(GoogleCalendarCredential.user_id == user_id)
        .first()
    )


def _delete_credential(db: Session, credential: GoogleCalendarCredential) -> None:
    db.delete(credential)
    db.commit()


class _InvalidGrantError(Exception):
    """Google's token endpoint answered `invalid_grant`.

    Its own exception rather than an HTTPException, because what it means
    depends on which grant was presented, and only the caller knows that:
    for a refresh token it is an authorisation that was revoked or expired,
    for an authorisation code it is a code that expired or was already used.
    """


def _oauth_error_code(response: httpx.Response) -> str | None:
    """The `error` field of an OAuth error response, if it has one.

    Only that field is read. The rest of the body is not logged or kept —
    `error_description` is Google's free text, and nothing about a rejected
    token call needs more than the code to act on.
    """
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    return error if isinstance(error, str) else None


def _post_to_google(url: str, data: dict[str, str]) -> dict[str, Any]:
    """One form-encoded token call, with every failure mapped to a message.

    Never logs or re-raises the response body: it carries the authorisation
    code, the client secret's rejection detail, and on success the refresh
    token itself.

    Raises _InvalidGrantError for `invalid_grant` and an HTTPException for
    everything else. Error responses from this endpoint arrive as HTTP 400
    (RFC 6749 §5.2), so the error *code* is what separates a grant that is
    gone from a deployment that is misconfigured — a wrong
    GOOGLE_CLIENT_SECRET is also a 400, as `invalid_client`. Matching on the
    status alone would treat that as every professional's authorisation
    having been revoked, and delete them all one scheduling attempt at a time.
    """
    try:
        response = httpx.post(
            url, data=data, timeout=settings.GOOGLE_CALENDAR_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("Google token request timed out: %s", url)
        raise HTTPException(
            status_code=504, detail=translate("meetings.google_timeout")
        ) from exc
    except httpx.HTTPStatusError as exc:
        error_code = _oauth_error_code(exc.response)
        if exc.response.status_code == 400 and error_code == "invalid_grant":
            raise _InvalidGrantError from exc
        logger.warning(
            "Google rejected a token request: HTTP %s (%s)",
            exc.response.status_code,
            error_code,
        )
        raise HTTPException(
            status_code=502, detail=translate("meetings.google_unavailable")
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Google token request failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502, detail=translate("meetings.google_unavailable")
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail=translate("meetings.google_unavailable")
        ) from exc
    return body


def exchange_calendar_token(
    db: Session, code: str, state: str, user: User
) -> GoogleCalendarCredential:
    """Exchange the authorisation code for a refresh token and store it.

    `user` is the logged-in caller, and the state has to have been issued to
    her — see _verify_state(). Verified before the code is exchanged, so a
    refused state never spends the code.

    Upsert rather than insert: re-authorising is the documented way out of a
    revoked or wrongly-scoped grant, and it has to replace what is there.
    """
    _require_configuration()
    _verify_state(state, user)

    try:
        body = _post_to_google(
            GOOGLE_TOKEN_URL,
            {
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI_MEET,
                "grant_type": "authorization_code",
            },
        )
    except _InvalidGrantError:
        # For an authorisation code this means the code expired or was already
        # exchanged — most often the return page being reloaded, which posts
        # the same single-use code twice. Nothing is wrong with Google or with
        # her account, but she has to start the consent again.
        raise HTTPException(
            status_code=400, detail=translate("meetings.calendar_state_invalid")
        ) from None

    refresh_token = body.get("refresh_token")
    if not refresh_token:
        # Google omits it when the account has already granted this client and
        # prompt=consent was not honoured. Nothing to store — a row without a
        # refresh token stops working within the hour.
        raise HTTPException(
            status_code=502, detail=translate("meetings.calendar_no_refresh_token")
        )

    granted_scope = body.get("scope", "")
    if settings.GOOGLE_CALENDAR_SCOPE not in granted_scope.split():
        # The consent screen lets her untick the calendar permission and
        # continue. Refusing here means the refusal names what is missing,
        # instead of the first scheduling attempt failing as a 403 from Google.
        raise HTTPException(
            status_code=403, detail=translate("meetings.calendar_scope_missing")
        )

    encrypted, key_version = encrypt_message(refresh_token)
    credential = get_credential(db, user.id)
    if credential is None:
        credential = GoogleCalendarCredential(user_id=user.id)
        db.add(credential)
    credential.refresh_token = encrypted
    credential.key_version = key_version
    credential.scope = granted_scope
    db.commit()
    db.refresh(credential)
    return credential


def _access_token(db: Session, user: User) -> str:
    """A fresh access token for this professional's calendar.

    Not cached: an access token lives an hour, scheduling a meeting is rare,
    and a second secret at rest would have to be encrypted and expired to save
    one HTTP call on an action that already makes two.
    """
    _require_configuration()
    credential = get_credential(db, user.id)
    if credential is None:
        # Tells her to connect her calendar first. Not something a client can
        # branch on — the detail is translated text, and other refusals are
        # 403s too — which is what GET /meetings/calendar/status is for.
        raise HTTPException(
            status_code=403, detail=translate("meetings.calendar_not_connected")
        )

    try:
        body = _post_to_google(
            GOOGLE_TOKEN_URL,
            {
                "refresh_token": decrypt_message(
                    credential.refresh_token, credential.key_version
                ),
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "grant_type": "refresh_token",
            },
        )
    except _InvalidGrantError:
        # A refresh token Google no longer honours: revoked at
        # myaccount.google.com, or expired — which a project in Testing does to
        # every grant after seven days. The row is dead weight that would
        # otherwise keep answering "connected" to the status endpoint while
        # every attempt failed as "Google is unavailable", so it goes, and she
        # is told to connect again.
        _delete_credential(db, credential)
        raise HTTPException(
            status_code=403, detail=translate("meetings.calendar_consent_expired")
        ) from None

    access_token = body.get("access_token")
    if not access_token:
        # A 200 without a token is not a revoked grant — that arrives as the
        # invalid_grant above. It is a malformed answer from Google, so the
        # credential is kept: deleting a grant that may be perfectly valid
        # would force her to reconnect over a glitch on Google's side.
        logger.warning("Google returned a token response without an access token")
        raise HTTPException(
            status_code=502, detail=translate("meetings.google_unavailable")
        )
    return str(access_token)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def _rfc3339(moment: datetime) -> str:
    """Naive-UTC (how this project stores time) to the instant Google wants."""
    return moment.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def create_meeting(
    db: Session,
    creator: User,
    title: str,
    scheduled_at: datetime,
    duration_minutes: int,
) -> tuple[str, str]:
    """Create a Calendar event with a Meet link. Returns (meet_link, event_id).

    No attendees, and sendUpdates=none. ABF-156 is explicit that there is no
    email — the forum announcement is the notification — and an attendee list
    is precisely the thing that makes Google send invitations of its own. It
    would also hand every member's address to every other member.
    """
    access_token = _access_token(db, creator)
    end = scheduled_at + timedelta(minutes=duration_minutes)
    payload = {
        "summary": title,
        "start": {"dateTime": _rfc3339(scheduled_at)},
        "end": {"dateTime": _rfc3339(end)},
        "conferenceData": {
            "createRequest": {
                # Google's idempotency key for the conference. A fresh uuid4
                # per call: reusing one returns the *same* Meet link, which
                # would quietly give two meetings one room.
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }

    try:
        response = httpx.post(
            GOOGLE_CALENDAR_EVENTS_URL,
            json=payload,
            # Without conferenceDataVersion=1 the API accepts the request and
            # silently drops conferenceData — an event with no Meet link.
            params={"conferenceDataVersion": 1, "sendUpdates": "none"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=settings.GOOGLE_CALENDAR_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("Google Calendar event creation timed out")
        raise HTTPException(
            status_code=504, detail=translate("meetings.google_timeout")
        ) from exc
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Google rejected the event creation: HTTP %s", exc.response.status_code
        )
        raise HTTPException(
            status_code=502, detail=translate("meetings.google_unavailable")
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Google Calendar event creation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502, detail=translate("meetings.google_unavailable")
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail=translate("meetings.google_unavailable")
        ) from exc

    event_id = body.get("id")
    meet_link = body.get("hangoutLink") or _entry_point(body)
    if not event_id or not meet_link:
        # An event without a join link is not a meeting anyone can attend, and
        # storing it would publish an announcement with a dead button.
        logger.warning("Google returned an event without a Meet link")
        raise HTTPException(
            status_code=502, detail=translate("meetings.google_no_meet_link")
        )
    return str(meet_link), str(event_id)


def _entry_point(body: dict[str, Any]) -> str | None:
    """The video entry point, for a response that carries no hangoutLink."""
    conference = body.get("conferenceData") or {}
    for entry in conference.get("entryPoints") or []:
        if entry.get("entryPointType") == "video" and entry.get("uri"):
            return str(entry["uri"])
    return None


def delete_event(db: Session, creator: User, event_id: str) -> None:
    """Best-effort removal of an event we created and then failed to record.

    Every failure is swallowed: this only ever runs while another error is
    already on its way to the caller, and replacing that error with this one
    would report the wrong problem. An event left behind is visible in the
    professional's own calendar and harmless — nobody was invited to it.
    """
    try:
        access_token = _access_token(db, creator)
        httpx.delete(
            f"{GOOGLE_CALENDAR_EVENTS_URL}/{event_id}",
            params={"sendUpdates": "none"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=settings.GOOGLE_CALENDAR_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.exception("Could not remove the orphaned calendar event %s", event_id)
