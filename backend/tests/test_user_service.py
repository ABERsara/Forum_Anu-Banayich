"""
Unit tests for user_service.get_pending_registrations.
"""

from datetime import UTC, datetime, timedelta

from app.core.constants import AccountStatus
from app.models.user import User
from app.services import user_service


def _make_user(db_session, email, status, created_at) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        account_status=status,
        created_at=created_at,
    )
    db_session.add(user)
    db_session.commit()
    return user


class TestGetPendingRegistrations:
    def test_returns_only_pending_and_partially_approved(self, db_session):
        now = datetime.now(UTC).replace(tzinfo=None)
        _make_user(db_session, "pending@example.com", AccountStatus.PENDING_APPROVAL, now)
        _make_user(db_session, "partial@example.com", AccountStatus.PARTIALLY_APPROVED, now)
        _make_user(db_session, "otp@example.com", AccountStatus.PENDING_OTP, now)
        _make_user(db_session, "active@example.com", AccountStatus.ACTIVE, now)
        _make_user(db_session, "rejected@example.com", AccountStatus.REJECTED, now)
        _make_user(db_session, "suspended@example.com", AccountStatus.SUSPENDED, now)
        _make_user(db_session, "cancelled@example.com", AccountStatus.CANCELLED, now)

        result = user_service.get_pending_registrations(db_session)

        emails = {u.email for u in result}
        assert emails == {"pending@example.com", "partial@example.com"}

    def test_orders_by_created_at_ascending(self, db_session):
        base = datetime.now(UTC).replace(tzinfo=None)
        newest = _make_user(
            db_session, "newest@example.com", AccountStatus.PENDING_APPROVAL, base + timedelta(minutes=2)
        )
        oldest = _make_user(db_session, "oldest@example.com", AccountStatus.PENDING_APPROVAL, base)
        middle = _make_user(
            db_session, "middle@example.com", AccountStatus.PARTIALLY_APPROVED, base + timedelta(minutes=1)
        )

        result = user_service.get_pending_registrations(db_session)

        assert [u.email for u in result] == [oldest.email, middle.email, newest.email]
