"""
Unit tests for the Google boundary (ABF-156).

Every HTTP call is faked. What is being pinned here is the shape of what we
send Google and what we do with what comes back — the two places where a
wrong assumption produces a meeting nobody can join, or an authorisation that
stops working an hour after it was granted.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import HTTPException
from jose import jwt

from app.core.config import settings
from app.core.constants import AccountStatus, ProfessionalDomain, UserRole
from app.core.encryption import decrypt_message
from app.core.i18n import translate
from app.core.security import ALGORITHM
from app.models.google_calendar_credential import GoogleCalendarCredential
from app.models.user import User
from app.services import google_meet_service

REFRESH_TOKEN = "1//refresh-token"
ACCESS_TOKEN = "ya29.access-token"
MEET_LINK = "https://meet.google.com/abc-defg-hij"


class _FakeResponse:
    def __init__(self, body: Any, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("POST", "https://google"), response=self
            )

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "client-secret")


@pytest.fixture
def professional(make_user) -> User:
    return make_user(
        email="pro@example.com",
        role=UserRole.PROFESSIONAL,
        account_status=AccountStatus.ACTIVE,
        professional_domain=ProfessionalDomain.LAWYER,
    )


#: What Google's token endpoint actually sends for a refresh token that was
#: revoked or has expired: HTTP 400, per RFC 6749 §5.2 — never a 200.
REVOKED_GRANT = {
    "error": "invalid_grant",
    "error_description": "Token has been expired or revoked.",
}


def _post_returning(
    monkeypatch, body: Any, recorder: list | None = None, status_code: int = 200
):
    def _post(url, **kwargs):
        if recorder is not None:
            recorder.append({"url": url, **kwargs})
        return _FakeResponse(body, status_code)

    monkeypatch.setattr(google_meet_service.httpx, "post", _post)


class TestAuthorizationUrl:
    def test_it_asks_for_an_offline_grant_with_a_fresh_consent(
        self, configured, professional
    ):
        url = google_meet_service.build_authorization_url(professional)

        query = parse_qs(urlparse(url).query)
        # Without these two, Google returns no refresh token — the first on a
        # first authorisation, the second on every one after it.
        assert query["access_type"] == ["offline"]
        assert query["prompt"] == ["consent"]
        assert query["scope"] == [settings.GOOGLE_CALENDAR_SCOPE]
        assert query["redirect_uri"] == [settings.GOOGLE_REDIRECT_URI_MEET]

    def test_the_state_carries_the_professional_and_nothing_else_is_accepted(
        self, configured, professional
    ):
        url = google_meet_service.build_authorization_url(professional)
        state = parse_qs(urlparse(url).query)["state"][0]

        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == professional.id
        assert payload["type"] == google_meet_service.STATE_TOKEN_TYPE

    def test_an_unconfigured_deployment_says_so_instead_of_calling_google(
        self, monkeypatch, professional
    ):
        monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")

        with pytest.raises(HTTPException) as exc_info:
            google_meet_service.build_authorization_url(professional)

        assert exc_info.value.status_code == 503


class TestExchangingTheCode:
    def _state_for(self, user: User) -> str:
        return jwt.encode(
            {
                "sub": user.id,
                "exp": datetime.now(UTC) + timedelta(minutes=5),
                "type": google_meet_service.STATE_TOKEN_TYPE,
            },
            settings.SECRET_KEY,
            algorithm=ALGORITHM,
        )

    def test_the_refresh_token_is_stored_encrypted(
        self, configured, db_session, professional, monkeypatch
    ):
        _post_returning(
            monkeypatch,
            {"refresh_token": REFRESH_TOKEN, "scope": settings.GOOGLE_CALENDAR_SCOPE},
        )

        credential = google_meet_service.exchange_calendar_token(
            db_session, "auth-code", self._state_for(professional)
        )

        assert credential.user_id == professional.id
        # Not the plaintext anywhere in the row, and recoverable from it.
        assert REFRESH_TOKEN not in credential.refresh_token
        assert (
            decrypt_message(credential.refresh_token, credential.key_version)
            == REFRESH_TOKEN
        )

    def test_authorising_again_replaces_the_row(
        self, configured, db_session, professional, monkeypatch
    ):
        _post_returning(
            monkeypatch,
            {"refresh_token": REFRESH_TOKEN, "scope": settings.GOOGLE_CALENDAR_SCOPE},
        )
        state = self._state_for(professional)
        google_meet_service.exchange_calendar_token(db_session, "code-1", state)

        _post_returning(
            monkeypatch,
            {"refresh_token": "1//second", "scope": settings.GOOGLE_CALENDAR_SCOPE},
        )
        google_meet_service.exchange_calendar_token(db_session, "code-2", state)

        rows = db_session.query(GoogleCalendarCredential).all()
        assert len(rows) == 1
        assert (
            decrypt_message(rows[0].refresh_token, rows[0].key_version) == "1//second"
        )

    def test_a_response_without_a_refresh_token_is_not_stored(
        self, configured, db_session, professional, monkeypatch
    ):
        _post_returning(
            monkeypatch,
            {"access_token": ACCESS_TOKEN, "scope": settings.GOOGLE_CALENDAR_SCOPE},
        )

        with pytest.raises(HTTPException) as exc_info:
            google_meet_service.exchange_calendar_token(
                db_session, "auth-code", self._state_for(professional)
            )

        assert exc_info.value.status_code == 502
        assert db_session.query(GoogleCalendarCredential).count() == 0

    def test_consent_without_the_calendar_scope_is_refused(
        self, configured, db_session, professional, monkeypatch
    ):
        """She can untick the calendar permission and continue — the refusal
        has to name that, not fail later inside scheduling."""
        _post_returning(
            monkeypatch,
            {
                "refresh_token": REFRESH_TOKEN,
                "scope": "https://www.googleapis.com/auth/userinfo.email",
            },
        )

        with pytest.raises(HTTPException) as exc_info:
            google_meet_service.exchange_calendar_token(
                db_session, "auth-code", self._state_for(professional)
            )

        assert exc_info.value.status_code == 403
        assert db_session.query(GoogleCalendarCredential).count() == 0

    def test_a_state_we_did_not_sign_is_rejected(
        self, configured, db_session, professional, monkeypatch
    ):
        forged = jwt.encode(
            {"sub": professional.id, "type": google_meet_service.STATE_TOKEN_TYPE},
            "not-our-secret",
            algorithm=ALGORITHM,
        )
        _post_returning(monkeypatch, {"refresh_token": REFRESH_TOKEN})

        with pytest.raises(HTTPException) as exc_info:
            google_meet_service.exchange_calendar_token(db_session, "code", forged)

        assert exc_info.value.status_code == 400

    def test_an_access_token_is_not_a_state(
        self, configured, db_session, professional, monkeypatch
    ):
        """Signed by us, but issued for logging in — a different grant."""
        access = jwt.encode(
            {
                "sub": professional.id,
                "exp": datetime.now(UTC) + timedelta(minutes=5),
                "type": "access",
            },
            settings.SECRET_KEY,
            algorithm=ALGORITHM,
        )
        _post_returning(monkeypatch, {"refresh_token": REFRESH_TOKEN})

        with pytest.raises(HTTPException) as exc_info:
            google_meet_service.exchange_calendar_token(db_session, "code", access)

        assert exc_info.value.status_code == 400

    def test_a_code_that_expired_or_was_used_asks_her_to_start_again(
        self, configured, db_session, professional, monkeypatch
    ):
        """
        invalid_grant on the *code* exchange — typically the callback page
        being reloaded, which presents the same single-use code twice. Not
        "Google is unavailable": nothing is wrong on Google's side.
        """
        _post_returning(
            monkeypatch,
            {"error": "invalid_grant", "error_description": "Bad Request"},
            status_code=400,
        )

        with pytest.raises(HTTPException) as exc_info:
            google_meet_service.exchange_calendar_token(
                db_session, "used-code", self._state_for(professional)
            )

        assert exc_info.value.status_code == 400
        assert db_session.query(GoogleCalendarCredential).count() == 0


def _connect(db_session, user: User) -> GoogleCalendarCredential:
    from app.core.encryption import encrypt_message

    encrypted, key_version = encrypt_message(REFRESH_TOKEN)
    credential = GoogleCalendarCredential(
        user_id=user.id,
        refresh_token=encrypted,
        key_version=key_version,
        scope=settings.GOOGLE_CALENDAR_SCOPE,
    )
    db_session.add(credential)
    db_session.commit()
    return credential


class TestCreatingTheEvent:
    def test_it_asks_for_a_meet_and_invites_nobody(
        self, configured, db_session, professional, monkeypatch
    ):
        _connect(db_session, professional)
        calls: list[dict[str, Any]] = []

        def _post(url, **kwargs):
            calls.append({"url": url, **kwargs})
            if url == google_meet_service.GOOGLE_TOKEN_URL:
                return _FakeResponse({"access_token": ACCESS_TOKEN})
            return _FakeResponse({"id": "evt-1", "hangoutLink": MEET_LINK})

        monkeypatch.setattr(google_meet_service.httpx, "post", _post)

        link, event_id = google_meet_service.create_meeting(
            db_session,
            professional,
            title="מפגש",
            scheduled_at=datetime(2026, 10, 1, 17, 0, 0),
            duration_minutes=60,
        )

        assert (link, event_id) == (MEET_LINK, "evt-1")
        event_call = calls[-1]
        payload = event_call["json"]
        # No attendees and sendUpdates=none: ABF-156 says there is no email,
        # and an attendee list is what makes Google send one.
        assert "attendees" not in payload
        assert event_call["params"]["sendUpdates"] == "none"
        # Without this the API accepts the request and silently returns an
        # event with no Meet link.
        assert event_call["params"]["conferenceDataVersion"] == 1
        assert payload["conferenceData"]["createRequest"]["conferenceSolutionKey"] == {
            "type": "hangoutsMeet"
        }
        # The stored instant, sent as UTC, with the end derived from it.
        assert payload["start"]["dateTime"] == "2026-10-01T17:00:00Z"
        assert payload["end"]["dateTime"] == "2026-10-01T18:00:00Z"

    def test_the_video_entry_point_is_used_when_there_is_no_hangout_link(
        self, configured, db_session, professional, monkeypatch
    ):
        _connect(db_session, professional)

        def _post(url, **kwargs):
            if url == google_meet_service.GOOGLE_TOKEN_URL:
                return _FakeResponse({"access_token": ACCESS_TOKEN})
            return _FakeResponse(
                {
                    "id": "evt-2",
                    "conferenceData": {
                        "entryPoints": [
                            {"entryPointType": "phone", "uri": "tel:+972"},
                            {"entryPointType": "video", "uri": MEET_LINK},
                        ]
                    },
                }
            )

        monkeypatch.setattr(google_meet_service.httpx, "post", _post)

        link, _ = google_meet_service.create_meeting(
            db_session,
            professional,
            title="מפגש",
            scheduled_at=datetime(2026, 10, 1, 17, 0, 0),
            duration_minutes=60,
        )

        assert link == MEET_LINK

    def test_an_event_without_a_link_is_a_failure_not_a_meeting(
        self, configured, db_session, professional, monkeypatch
    ):
        _connect(db_session, professional)

        def _post(url, **kwargs):
            if url == google_meet_service.GOOGLE_TOKEN_URL:
                return _FakeResponse({"access_token": ACCESS_TOKEN})
            return _FakeResponse({"id": "evt-3"})

        monkeypatch.setattr(google_meet_service.httpx, "post", _post)

        with pytest.raises(HTTPException) as exc_info:
            google_meet_service.create_meeting(
                db_session,
                professional,
                title="מפגש",
                scheduled_at=datetime(2026, 10, 1, 17, 0, 0),
                duration_minutes=60,
            )

        assert exc_info.value.status_code == 502

    def test_a_timeout_is_reported_as_one(
        self, configured, db_session, professional, monkeypatch
    ):
        _connect(db_session, professional)

        def _post(url, **kwargs):
            if url == google_meet_service.GOOGLE_TOKEN_URL:
                return _FakeResponse({"access_token": ACCESS_TOKEN})
            raise httpx.TimeoutException("too slow")

        monkeypatch.setattr(google_meet_service.httpx, "post", _post)

        with pytest.raises(HTTPException) as exc_info:
            google_meet_service.create_meeting(
                db_session,
                professional,
                title="מפגש",
                scheduled_at=datetime(2026, 10, 1, 17, 0, 0),
                duration_minutes=60,
            )

        assert exc_info.value.status_code == 504

    def test_without_a_linked_calendar_nothing_is_sent_to_google(
        self, configured, db_session, professional, monkeypatch
    ):
        def _post(url, **kwargs):
            raise AssertionError("Google must not be called without a credential")

        monkeypatch.setattr(google_meet_service.httpx, "post", _post)

        with pytest.raises(HTTPException) as exc_info:
            google_meet_service.create_meeting(
                db_session,
                professional,
                title="מפגש",
                scheduled_at=datetime(2026, 10, 1, 17, 0, 0),
                duration_minutes=60,
            )

        assert exc_info.value.status_code == 403

    def _schedule(self, db_session, professional):
        return google_meet_service.create_meeting(
            db_session,
            professional,
            title="מפגש",
            scheduled_at=datetime(2026, 10, 1, 17, 0, 0),
            duration_minutes=60,
        )

    def test_a_revoked_grant_forgets_the_credential(
        self, configured, db_session, professional, monkeypatch
    ):
        """
        Google answers a revoked or expired refresh token with HTTP 400 and
        invalid_grant. Keeping the row would leave the status endpoint
        reporting a connected calendar while every attempt failed as "Google is
        unavailable" — with nothing telling her that reconnecting is the fix.
        """
        _connect(db_session, professional)
        _post_returning(monkeypatch, REVOKED_GRANT, status_code=400)

        with pytest.raises(HTTPException) as exc_info:
            self._schedule(db_session, professional)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == translate("meetings.calendar_consent_expired")
        assert db_session.query(GoogleCalendarCredential).count() == 0

    def test_a_misconfigured_client_does_not_wipe_the_credential(
        self, configured, db_session, professional, monkeypatch
    ):
        """
        A wrong GOOGLE_CLIENT_SECRET is also a 400 — as invalid_client. It says
        nothing about her grant, which is still valid; treating every 400 as a
        revocation would delete each professional's authorisation on her next
        attempt, over a deployment mistake.
        """
        _connect(db_session, professional)
        _post_returning(
            monkeypatch,
            {"error": "invalid_client", "error_description": "Unauthorized"},
            status_code=400,
        )

        with pytest.raises(HTTPException) as exc_info:
            self._schedule(db_session, professional)

        assert exc_info.value.status_code == 502
        assert db_session.query(GoogleCalendarCredential).count() == 1

    def test_a_success_without_a_token_is_a_glitch_not_a_revocation(
        self, configured, db_session, professional, monkeypatch
    ):
        """A malformed 200 keeps the credential — it may be perfectly valid."""
        _connect(db_session, professional)
        _post_returning(monkeypatch, {"token_type": "Bearer"})

        with pytest.raises(HTTPException) as exc_info:
            self._schedule(db_session, professional)

        assert exc_info.value.status_code == 502
        assert db_session.query(GoogleCalendarCredential).count() == 1
