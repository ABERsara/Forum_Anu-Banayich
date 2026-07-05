"""
Integration tests for auth endpoints: register, verify_otp, resend_otp, login, refresh.

Each test runs against an isolated in-memory SQLite DB (see conftest.py).
"""

from datetime import UTC, datetime, timedelta

from jose import jwt as jose_jwt

from app.core.config import settings
from app.core.constants import AccountStatus
from app.core.security import ALGORITHM
from app.models.user import User

BASE = "/api/v1/auth"

VALID_PAYLOAD = {
    "first_name": "שרה",
    "last_name": "לוי",
    "email": "sarah@example.com",
    "phone": "0501234567",
    "birth_date": "1985-03-15",
    "user_type": "widow",
    "sector": "sephardic",
    "id_number": "123456789",
    "password": "StrongPass1!",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _register(client, payload=None):
    return await client.post(f"{BASE}/register", json=payload or VALID_PAYLOAD)


def _get_user(db_session, email=VALID_PAYLOAD["email"]) -> User:
    db_session.expire_all()
    return db_session.query(User).filter_by(email=email).first()


async def _register_and_verify(client, db_session, email=VALID_PAYLOAD["email"]):
    """Register + verify OTP. Leaves the user in PENDING_APPROVAL status."""
    await _register(client, {**VALID_PAYLOAD, "email": email})
    otp = _get_user(db_session, email).otp_code
    await client.post(f"{BASE}/verify-otp", json={"email": email, "otp_code": otp})
    return _get_user(db_session, email)


async def _register_verify_and_activate(client, db_session, email=VALID_PAYLOAD["email"]):
    """Register + verify OTP + manually promote to ACTIVE (the approval step)."""
    user = await _register_and_verify(client, db_session, email)
    user.account_status = AccountStatus.ACTIVE
    db_session.commit()
    return user


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

class TestRegister:
    async def test_success_returns_201(self, client):
        r = await _register(client)
        assert r.status_code == 201

    async def test_success_account_status_is_pending_otp(self, client, db_session):
        await _register(client)
        assert _get_user(db_session).account_status == AccountStatus.PENDING_OTP

    async def test_success_returns_user_id(self, client):
        r = await _register(client)
        assert "user_id" in r.json()

    async def test_success_otp_saved_in_db(self, client, db_session):
        await _register(client)
        user = _get_user(db_session)
        assert user is not None
        assert user.otp_code is not None
        assert len(user.otp_code) == 6
        assert user.otp_code.isdigit()

    async def test_success_otp_expiry_set(self, client, db_session):
        await _register(client)
        user = _get_user(db_session)
        assert user.otp_expires_at is not None
        # otp_expires_at is stored as naive UTC — compare against UTC now (stripped of tzinfo)
        assert user.otp_expires_at > datetime.now(UTC).replace(tzinfo=None)

    async def test_duplicate_email_returns_409(self, client):
        await _register(client)
        r = await _register(client)
        assert r.status_code == 409

    async def test_duplicate_email_hebrew_error(self, client):
        await _register(client)
        r = await _register(client)
        assert "מייל" in r.json()["detail"]

    async def test_invalid_email_returns_422(self, client):
        r = await _register(client, {**VALID_PAYLOAD, "email": "not-an-email"})
        assert r.status_code == 422

    async def test_short_password_returns_422(self, client):
        r = await _register(client, {**VALID_PAYLOAD, "password": "short"})
        assert r.status_code == 422

    async def test_invalid_phone_returns_422(self, client):
        r = await _register(client, {**VALID_PAYLOAD, "phone": "abc-xyz"})
        assert r.status_code == 422

    async def test_missing_required_field_returns_422(self, client):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "first_name"}
        r = await _register(client, payload)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# verify_otp
# ---------------------------------------------------------------------------

class TestVerifyOtp:
    async def _register_and_get_otp(self, client, db_session, email=VALID_PAYLOAD["email"]):
        await _register(client, {**VALID_PAYLOAD, "email": email})
        return _get_user(db_session, email).otp_code

    async def test_correct_otp_returns_200(self, client, db_session):
        otp = await self._register_and_get_otp(client, db_session)
        r = await client.post(f"{BASE}/verify-otp", json={"email": VALID_PAYLOAD["email"], "otp_code": otp})
        assert r.status_code == 200

    async def test_correct_otp_status_becomes_pending_approval(self, client, db_session):
        otp = await self._register_and_get_otp(client, db_session)
        await client.post(f"{BASE}/verify-otp", json={"email": VALID_PAYLOAD["email"], "otp_code": otp})
        assert _get_user(db_session).account_status == AccountStatus.PENDING_APPROVAL

    async def test_correct_otp_clears_otp_from_db(self, client, db_session):
        otp = await self._register_and_get_otp(client, db_session)
        await client.post(f"{BASE}/verify-otp", json={"email": VALID_PAYLOAD["email"], "otp_code": otp})
        user = _get_user(db_session)
        assert user.otp_code is None
        assert user.otp_expires_at is None

    async def test_wrong_otp_returns_400(self, client, db_session):
        await self._register_and_get_otp(client, db_session)
        r = await client.post(f"{BASE}/verify-otp", json={"email": VALID_PAYLOAD["email"], "otp_code": "000000"})
        assert r.status_code == 400

    async def test_wrong_otp_generic_message(self, client, db_session):
        await self._register_and_get_otp(client, db_session)
        r = await client.post(f"{BASE}/verify-otp", json={"email": VALID_PAYLOAD["email"], "otp_code": "000000"})
        assert r.json()["detail"] == "הפרטים שהוזנו שגויים"

    async def test_nonexistent_email_returns_400(self, client):
        r = await client.post(f"{BASE}/verify-otp", json={"email": "nobody@example.com", "otp_code": "123456"})
        assert r.status_code == 400

    async def test_nonexistent_email_same_message_as_wrong_otp(self, client, db_session):
        """User enumeration protection: identical response for missing user and wrong OTP."""
        await self._register_and_get_otp(client, db_session)
        r_wrong = await client.post(f"{BASE}/verify-otp", json={"email": VALID_PAYLOAD["email"], "otp_code": "000000"})
        r_missing = await client.post(f"{BASE}/verify-otp", json={"email": "nobody@example.com", "otp_code": "000000"})
        assert r_wrong.status_code == r_missing.status_code
        assert r_wrong.json()["detail"] == r_missing.json()["detail"]

    async def test_expired_otp_returns_400(self, client, db_session):
        otp = await self._register_and_get_otp(client, db_session)
        user = _get_user(db_session)
        user.otp_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db_session.commit()
        r = await client.post(f"{BASE}/verify-otp", json={"email": VALID_PAYLOAD["email"], "otp_code": otp})
        assert r.status_code == 400

    async def test_expired_otp_distinct_message(self, client, db_session):
        otp = await self._register_and_get_otp(client, db_session)
        user = _get_user(db_session)
        user.otp_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db_session.commit()
        r = await client.post(f"{BASE}/verify-otp", json={"email": VALID_PAYLOAD["email"], "otp_code": otp})
        assert r.json()["detail"] == "קוד האימות פג תוקף"


# ---------------------------------------------------------------------------
# resend_otp
# ---------------------------------------------------------------------------

class TestResendOtp:
    async def test_success_returns_200(self, client):
        await _register(client)
        r = await client.post(f"{BASE}/resend-otp", json={"email": VALID_PAYLOAD["email"]})
        assert r.status_code == 200

    async def test_resend_updates_otp_in_db(self, client, db_session):
        await _register(client)
        old_otp = _get_user(db_session).otp_code
        await client.post(f"{BASE}/resend-otp", json={"email": VALID_PAYLOAD["email"]})
        user = _get_user(db_session)
        assert user.otp_code is not None
        assert user.otp_code != old_otp
        assert user.otp_expires_at is not None

    async def test_resend_new_otp_is_valid(self, client, db_session):
        """New OTP from resend must work with verify-otp."""
        await _register(client)
        await client.post(f"{BASE}/resend-otp", json={"email": VALID_PAYLOAD["email"]})
        new_otp = _get_user(db_session).otp_code
        r = await client.post(f"{BASE}/verify-otp", json={"email": VALID_PAYLOAD["email"], "otp_code": new_otp})
        assert r.status_code == 200

    async def test_nonexistent_email_returns_400(self, client):
        r = await client.post(f"{BASE}/resend-otp", json={"email": "nobody@example.com"})
        assert r.status_code == 400

    async def test_after_verify_resend_returns_400(self, client, db_session):
        """User in PENDING_APPROVAL cannot resend OTP."""
        await _register(client)
        otp = _get_user(db_session).otp_code
        await client.post(f"{BASE}/verify-otp", json={"email": VALID_PAYLOAD["email"], "otp_code": otp})
        r = await client.post(f"{BASE}/resend-otp", json={"email": VALID_PAYLOAD["email"]})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

LOGIN_PAYLOAD = {"email": VALID_PAYLOAD["email"], "password": VALID_PAYLOAD["password"]}


class TestLogin:
    async def test_missing_email_returns_422(self, client):
        r = await client.post(f"{BASE}/login", json={"password": "StrongPass1!"})
        assert r.status_code == 422

    async def test_missing_password_returns_422(self, client):
        r = await client.post(f"{BASE}/login", json={"email": "sarah@example.com"})
        assert r.status_code == 422

    async def test_invalid_email_returns_422(self, client):
        r = await client.post(f"{BASE}/login", json={"email": "not-an-email", "password": "StrongPass1!"})
        assert r.status_code == 422

    async def test_active_user_returns_200(self, client, db_session):
        await _register_verify_and_activate(client, db_session)
        r = await client.post(f"{BASE}/login", json=LOGIN_PAYLOAD)
        assert r.status_code == 200

    async def test_response_has_all_token_fields(self, client, db_session):
        await _register_verify_and_activate(client, db_session)
        r = await client.post(f"{BASE}/login", json=LOGIN_PAYLOAD)
        body = r.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_wrong_password_returns_401(self, client, db_session):
        await _register_verify_and_activate(client, db_session)
        r = await client.post(f"{BASE}/login", json={"email": VALID_PAYLOAD["email"], "password": "WrongPass1!"})
        assert r.status_code == 401

    async def test_nonexistent_email_same_response_as_wrong_password(self, client, db_session):
        """User enumeration protection: identical 401 for missing user and wrong password."""
        await _register_verify_and_activate(client, db_session)
        r_wrong = await client.post(f"{BASE}/login", json={"email": VALID_PAYLOAD["email"], "password": "WrongPass1!"})
        r_missing = await client.post(f"{BASE}/login", json={"email": "nobody@example.com", "password": "WrongPass1!"})
        assert r_wrong.status_code == r_missing.status_code == 401
        assert r_wrong.json()["detail"] == r_missing.json()["detail"]

    async def test_pending_otp_user_returns_403(self, client):
        """User must have ACTIVE status to login."""
        await _register(client)
        r = await client.post(f"{BASE}/login", json=LOGIN_PAYLOAD)
        assert r.status_code == 403

    async def test_pending_approval_user_returns_403(self, client, db_session):
        await _register_and_verify(client, db_session)
        r = await client.post(f"{BASE}/login", json=LOGIN_PAYLOAD)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------

class TestRefresh:
    async def test_missing_token_returns_422(self, client):
        r = await client.post(f"{BASE}/refresh", json={})
        assert r.status_code == 422

    async def test_invalid_token_returns_401(self, client):
        r = await client.post(f"{BASE}/refresh", json={"refresh_token": "not.a.valid.jwt"})
        assert r.status_code == 401

    async def test_success_returns_new_access_token(self, client, db_session):
        await _register_verify_and_activate(client, db_session)
        login_r = await client.post(f"{BASE}/login", json=LOGIN_PAYLOAD)
        refresh_tok = login_r.json()["refresh_token"]
        r = await client.post(f"{BASE}/refresh", json={"refresh_token": refresh_tok})
        assert r.status_code == 200
        assert "access_token" in r.json()

    async def test_new_access_token_has_correct_type_claim(self, client, db_session):
        await _register_verify_and_activate(client, db_session)
        login_r = await client.post(f"{BASE}/login", json=LOGIN_PAYLOAD)
        refresh_tok = login_r.json()["refresh_token"]
        r = await client.post(f"{BASE}/refresh", json={"refresh_token": refresh_tok})
        payload = jose_jwt.decode(r.json()["access_token"], settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload.get("type") == "access"

    async def test_same_refresh_token_returned(self, client, db_session):
        await _register_verify_and_activate(client, db_session)
        login_r = await client.post(f"{BASE}/login", json=LOGIN_PAYLOAD)
        refresh_tok = login_r.json()["refresh_token"]
        r = await client.post(f"{BASE}/refresh", json={"refresh_token": refresh_tok})
        assert r.json()["refresh_token"] == refresh_tok

    async def test_access_token_used_as_refresh_returns_401(self, client, db_session):
        """Tokens issued as 'access' must not be accepted as refresh tokens."""
        await _register_verify_and_activate(client, db_session)
        login_r = await client.post(f"{BASE}/login", json=LOGIN_PAYLOAD)
        access_tok = login_r.json()["access_token"]
        r = await client.post(f"{BASE}/refresh", json={"refresh_token": access_tok})
        assert r.status_code == 401
