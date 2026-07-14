"""
Unit tests for user_service registration functions.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.constants import AccountStatus, AuditAction, UserRole
from app.models.audit import AuditLog
from app.models.user import User
from app.services import user_service


def _make_user(db_session: Session, email: str, status: AccountStatus, created_at: datetime) -> User:
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


def _make_admin(db_session: Session, email: str) -> User:
    admin = User(
        email=email,
        password_hash="hashed",
        first_name="Admin",
        last_name="User",
        role=UserRole.ADMIN,
        account_status=AccountStatus.ACTIVE,
    )
    db_session.add(admin)
    db_session.commit()
    return admin


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


class TestGetActiveUsers:
    def test_returns_only_active_users_with_role_user(self, db_session: Session) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        _make_user(db_session, "active@example.com", AccountStatus.ACTIVE, now)
        _make_user(db_session, "pending@example.com", AccountStatus.PENDING_APPROVAL, now)
        _make_user(db_session, "suspended@example.com", AccountStatus.SUSPENDED, now)
        _make_user(db_session, "rejected@example.com", AccountStatus.REJECTED, now)
        _make_admin(db_session, "admin@example.com")

        result = user_service.get_active_users(db_session)

        emails = {u.email for u in result}
        assert emails == {"active@example.com"}

    def test_orders_by_created_at_ascending(self, db_session: Session) -> None:
        base = datetime.now(UTC).replace(tzinfo=None)
        newest = _make_user(
            db_session, "newest@example.com", AccountStatus.ACTIVE, base + timedelta(minutes=2)
        )
        oldest = _make_user(db_session, "oldest@example.com", AccountStatus.ACTIVE, base)
        middle = _make_user(
            db_session, "middle@example.com", AccountStatus.ACTIVE, base + timedelta(minutes=1)
        )

        result = user_service.get_active_users(db_session)

        assert [u.email for u in result] == [oldest.email, middle.email, newest.email]


class TestApproveRegistration:
    def test_first_approval_sets_partially_approved(self, db_session: Session) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "pending@example.com", AccountStatus.PENDING_APPROVAL, now)
        admin = _make_admin(db_session, "admin1@example.com")

        result = user_service.approve_registration(db_session, user.id, admin)

        assert result.account_status == AccountStatus.PARTIALLY_APPROVED
        assert result.first_approver_id == admin.id
        assert result.second_approver_id is None

    def test_first_approval_does_not_send_email(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called = []
        monkeypatch.setattr(user_service, "send_approval_email", lambda *a: called.append(a))
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "pending@example.com", AccountStatus.PENDING_APPROVAL, now)
        admin = _make_admin(db_session, "admin1@example.com")

        user_service.approve_registration(db_session, user.id, admin)

        assert called == []

    def test_second_approval_by_different_admin_activates_and_sends_email(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent = []
        monkeypatch.setattr(user_service, "send_approval_email", lambda *a: sent.append(a))
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "pending@example.com", AccountStatus.PENDING_APPROVAL, now)
        admin_a = _make_admin(db_session, "admin1@example.com")
        admin_b = _make_admin(db_session, "admin2@example.com")

        user_service.approve_registration(db_session, user.id, admin_a)
        result = user_service.approve_registration(db_session, user.id, admin_b)

        assert result.account_status == AccountStatus.ACTIVE
        assert result.first_approver_id == admin_a.id
        assert result.second_approver_id == admin_b.id
        assert result.approved_at is not None
        assert sent == [(user.email, user.first_name)]

    def test_same_admin_cannot_approve_twice(self, db_session: Session) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "pending@example.com", AccountStatus.PENDING_APPROVAL, now)
        admin = _make_admin(db_session, "admin1@example.com")

        user_service.approve_registration(db_session, user.id, admin)

        with pytest.raises(HTTPException) as exc_info:
            user_service.approve_registration(db_session, user.id, admin)
        assert exc_info.value.status_code == 400

    def test_cannot_approve_non_pending_registration(self, db_session: Session) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "active@example.com", AccountStatus.ACTIVE, now)
        admin = _make_admin(db_session, "admin1@example.com")

        with pytest.raises(HTTPException) as exc_info:
            user_service.approve_registration(db_session, user.id, admin)
        assert exc_info.value.status_code == 400

    def test_approve_nonexistent_user_raises_404(self, db_session: Session) -> None:
        admin = _make_admin(db_session, "admin1@example.com")

        with pytest.raises(HTTPException) as exc_info:
            user_service.approve_registration(db_session, "does-not-exist", admin)
        assert exc_info.value.status_code == 404

    def test_creates_audit_log_entry(self, db_session: Session) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "pending@example.com", AccountStatus.PENDING_APPROVAL, now)
        admin = _make_admin(db_session, "admin1@example.com")

        user_service.approve_registration(db_session, user.id, admin)

        logs = db_session.query(AuditLog).filter(AuditLog.entity_id == user.id).all()
        assert len(logs) == 1
        assert logs[0].action == AuditAction.USER_APPROVED
        assert logs[0].actor_id == admin.id
        details = logs[0].details
        assert details is not None
        assert details["previous_status"] == AccountStatus.PENDING_APPROVAL
        assert details["new_status"] == AccountStatus.PARTIALLY_APPROVED

    def test_creates_audit_log_for_second_approval(self, db_session: Session) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "pending@example.com", AccountStatus.PENDING_APPROVAL, now)
        admin_a = _make_admin(db_session, "admin1@example.com")
        admin_b = _make_admin(db_session, "admin2@example.com")

        user_service.approve_registration(db_session, user.id, admin_a)
        user_service.approve_registration(db_session, user.id, admin_b)

        logs = db_session.query(AuditLog).filter(AuditLog.entity_id == user.id).order_by(AuditLog.timestamp).all()
        assert len(logs) == 2
        second_log = logs[1]
        assert second_log.action == AuditAction.USER_APPROVED
        assert second_log.actor_id == admin_b.id
        details = second_log.details
        assert details is not None
        assert details["previous_status"] == AccountStatus.PARTIALLY_APPROVED
        assert details["new_status"] == AccountStatus.ACTIVE


class TestRejectRegistration:
    def test_reject_sets_status_and_reason_and_sends_email(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent = []
        monkeypatch.setattr(user_service, "send_rejection_email", lambda *a: sent.append(a))
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "pending@example.com", AccountStatus.PENDING_APPROVAL, now)
        admin = _make_admin(db_session, "admin1@example.com")

        result = user_service.reject_registration(db_session, user.id, admin, "not enough documents")

        assert result.account_status == AccountStatus.REJECTED
        assert result.rejection_reason == "not enough documents"
        assert sent == [(user.email, user.first_name, "not enough documents")]

    def test_reject_nonexistent_user_raises_404(self, db_session: Session) -> None:
        admin = _make_admin(db_session, "admin1@example.com")

        with pytest.raises(HTTPException) as exc_info:
            user_service.reject_registration(db_session, "does-not-exist", admin, "some reason")
        assert exc_info.value.status_code == 404

    def test_cannot_reject_non_pending_registration(self, db_session: Session) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "rejected@example.com", AccountStatus.REJECTED, now)
        admin = _make_admin(db_session, "admin1@example.com")

        with pytest.raises(HTTPException) as exc_info:
            user_service.reject_registration(db_session, user.id, admin, "some reason")
        assert exc_info.value.status_code == 400

    def test_creates_audit_log_entry(self, db_session: Session) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "pending@example.com", AccountStatus.PENDING_APPROVAL, now)
        admin = _make_admin(db_session, "admin1@example.com")

        user_service.reject_registration(db_session, user.id, admin, "not enough documents")

        logs = db_session.query(AuditLog).filter(AuditLog.entity_id == user.id).all()
        assert len(logs) == 1
        assert logs[0].action == AuditAction.USER_REJECTED
        assert logs[0].actor_id == admin.id
        details = logs[0].details
        assert details is not None
        assert details["reason"] == "not enough documents"


class TestSuspendUser:
    def test_suspends_active_user(self, db_session: Session) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "active@example.com", AccountStatus.ACTIVE, now)
        admin = _make_admin(db_session, "admin1@example.com")

        before = datetime.now(UTC)
        result = user_service.suspend_user(db_session, user.id, admin, 48, "spam behaviour")
        after = datetime.now(UTC)

        assert result.account_status == AccountStatus.SUSPENDED
        assert result.is_suspended is True
        assert result.suspended_until is not None
        suspended_until = result.suspended_until.replace(tzinfo=UTC)
        assert before + timedelta(hours=48) <= suspended_until <= after + timedelta(hours=48)

    def test_sends_suspension_notification_email(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent = []
        monkeypatch.setattr(
            user_service, "send_suspension_notification", lambda *a: sent.append(a)
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "active@example.com", AccountStatus.ACTIVE, now)
        admin = _make_admin(db_session, "admin1@example.com")

        user_service.suspend_user(db_session, user.id, admin, 48, "spam behaviour")

        assert sent == [(user.email, 48, "spam behaviour")]

    def test_creates_audit_log_entry(self, db_session: Session) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "active@example.com", AccountStatus.ACTIVE, now)
        admin = _make_admin(db_session, "admin1@example.com")

        user_service.suspend_user(db_session, user.id, admin, 48, "spam behaviour")

        logs = db_session.query(AuditLog).filter(AuditLog.entity_id == user.id).all()
        assert len(logs) == 1
        assert logs[0].action == AuditAction.USER_SUSPENDED
        assert logs[0].actor_id == admin.id
        details = logs[0].details
        assert details is not None
        assert details["hours"] == 48
        assert details["reason"] == "spam behaviour"

    def test_cannot_suspend_non_active_user(self, db_session: Session) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = _make_user(db_session, "pending@example.com", AccountStatus.PENDING_APPROVAL, now)
        admin = _make_admin(db_session, "admin1@example.com")

        with pytest.raises(HTTPException) as exc_info:
            user_service.suspend_user(db_session, user.id, admin, 48, "spam behaviour")
        assert exc_info.value.status_code == 400

    def test_cannot_suspend_non_user_role(self, db_session: Session) -> None:
        admin = _make_admin(db_session, "admin1@example.com")
        other_admin = _make_admin(db_session, "admin2@example.com")

        with pytest.raises(HTTPException) as exc_info:
            user_service.suspend_user(db_session, other_admin.id, admin, 48, "spam behaviour")
        assert exc_info.value.status_code == 400

    def test_suspend_nonexistent_user_raises_404(self, db_session: Session) -> None:
        admin = _make_admin(db_session, "admin1@example.com")

        with pytest.raises(HTTPException) as exc_info:
            user_service.suspend_user(db_session, "does-not-exist", admin, 48, "spam behaviour")
        assert exc_info.value.status_code == 404
