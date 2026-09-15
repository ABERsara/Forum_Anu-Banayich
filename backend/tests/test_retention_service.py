"""
Tests for message retention, account-deletion message handling, and the
GDPR self-export (ABF-117, spec §5.3/§9.4/§9.5).

Three layers:
  - TestPurgeExpiredDirectMessages exercises the scheduled 3-year job.
  - TestPurgeUserDirectMessages / TestDeleteOwnAccount exercise the
    account-deletion message/report handling directly against
    retention_service / user_service.
  - TestDeleteMyAccountEndpoint / TestExportMyMessagesEndpoint go through the
    real HTTP routes, hitting the API directly rather than through any UI —
    required by §4.2's positive AND negative permission checks.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.constants import (
    AccountStatus,
    AuditAction,
    ReportDecision,
    ReportReason,
    ReportTargetType,
    Sector,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_active_user, get_current_user
from app.core.encryption import encrypt_message
from app.main import app
from app.models.audit import AuditLog
from app.models.forum import DirectMessage
from app.models.report import Report
from app.models.user import User
from app.services import retention_service, user_service

MESSAGES_EXPORT_URL = "/api/v1/users/me/messages/export"
DELETE_ACCOUNT_URL = "/api/v1/users/me"


def _make_user(
    db_session,
    email: str,
    user_type: UserType | None = None,
    sector: Sector | None = None,
    role: UserRole = UserRole.USER,
    account_status: AccountStatus = AccountStatus.ACTIVE,
) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        user_type=user_type,
        sector=sector,
        account_status=account_status,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login_as(user: User) -> None:
    """Bypass real JWT auth, same technique as test_direct_messages.py."""
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_active_user] = lambda: user


def _make_message(
    db_session, sender: User, recipient: User, content: str, created_at: datetime
) -> DirectMessage:
    encrypted, key_version = encrypt_message(content)
    message = DirectMessage(
        sender_id=sender.id,
        recipient_id=recipient.id,
        conversation_key=f"{sender.id}:{recipient.id}",
        content=encrypted,
        key_version=key_version,
        created_at=created_at,
    )
    db_session.add(message)
    db_session.commit()
    return message


def _report(
    db_session, reporter: User, message: DirectMessage, decision: ReportDecision
) -> Report:
    report = Report(
        reporter_id=reporter.id,
        target_type=ReportTargetType.DIRECT_MESSAGE,
        target_id=message.id,
        reported_user_id=message.sender_id,
        reason=ReportReason.HARASSMENT,
        decision=decision,
    )
    db_session.add(report)
    db_session.commit()
    return report


# ---------------------------------------------------------------------------
# purge_expired_direct_messages() — the scheduled job
# ---------------------------------------------------------------------------


class TestPurgeExpiredDirectMessages:
    def test_deletes_only_messages_past_the_retention_window(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        now = datetime(2026, 9, 7, 12, 0, 0)
        old = _make_message(
            db_session,
            a,
            b,
            "ישנה",
            now - timedelta(days=settings.DIRECT_MESSAGE_RETENTION_DAYS + 1),
        )
        recent = _make_message(
            db_session,
            a,
            b,
            "חדשה",
            now - timedelta(days=1),
        )
        old_id, recent_id = old.id, recent.id

        deleted_ids = retention_service.purge_expired_direct_messages(db_session)

        assert deleted_ids == [old_id]
        remaining = db_session.query(DirectMessage).all()
        assert [m.id for m in remaining] == [recent_id]

    def test_no_expired_messages_is_a_noop(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _make_message(db_session, a, b, "חדשה", datetime.now())

        assert retention_service.purge_expired_direct_messages(db_session) == []
        assert db_session.query(DirectMessage).count() == 1

    def test_skips_an_expired_message_under_an_open_report(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        now = datetime(2026, 9, 7, 12, 0, 0)
        old = _make_message(
            db_session,
            a,
            b,
            "ישנה ומדווחת",
            now - timedelta(days=settings.DIRECT_MESSAGE_RETENTION_DAYS + 1),
        )
        _report(db_session, b, old, ReportDecision.PENDING)

        deleted_ids = retention_service.purge_expired_direct_messages(db_session)

        assert deleted_ids == []
        assert (
            db_session.query(DirectMessage).filter(DirectMessage.id == old.id).first()
        )

    def test_writes_an_audit_entry_with_no_human_actor(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        now = datetime(2026, 9, 7, 12, 0, 0)
        old = _make_message(
            db_session,
            a,
            b,
            "ישנה",
            now - timedelta(days=settings.DIRECT_MESSAGE_RETENTION_DAYS + 1),
        )
        old_id = old.id

        retention_service.purge_expired_direct_messages(db_session)

        entry = db_session.query(AuditLog).filter(AuditLog.entity_id == old_id).first()
        assert entry is not None
        assert entry.actor_id == retention_service.SYSTEM_ACTOR_ID
        assert entry.action == AuditAction.DIRECT_MESSAGE_PRUNED


# ---------------------------------------------------------------------------
# purge_user_direct_messages() — the message side of account deletion
# ---------------------------------------------------------------------------


class TestPurgeUserDirectMessages:
    def test_deletes_every_message_the_user_sent_or_received(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        c = _make_user(db_session, "c@example.com", UserType.WIDOW, Sector.HASIDIC)
        now = datetime.now()
        _make_message(db_session, a, b, "a שלח ל-b", now)
        _make_message(db_session, b, a, "b שלח ל-a", now)
        _make_message(db_session, b, c, "לא נוגע ל-a", now)

        result, entries = retention_service.purge_user_direct_messages(db_session, a)

        assert len(result["deleted_message_ids"]) == 2
        assert len(entries) == 2
        assert db_session.query(DirectMessage).count() == 1

    def test_no_messages_is_a_noop(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)

        result, entries = retention_service.purge_user_direct_messages(db_session, a)

        assert result == {"deleted_message_ids": [], "closed_report_ids": []}
        assert entries == []

    def test_deleting_the_reported_on_user_deletes_message_and_closes_report(
        self, db_session
    ):
        """spec's 'נמחק המדווח-עליו' — the message's sender is deleted."""
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        message = _make_message(db_session, sender, recipient, "תוכן", datetime.now())
        report = _report(db_session, recipient, message, ReportDecision.PENDING)

        result, entries = retention_service.purge_user_direct_messages(
            db_session, sender
        )

        assert result["deleted_message_ids"] == [message.id]
        assert result["closed_report_ids"] == [report.id]
        assert db_session.query(DirectMessage).count() == 0
        # Not committed by purge_user_direct_messages() on purpose (see its
        # docstring) — `report` is still the session's identity-mapped
        # instance, so the mutation is visible without a refresh; refreshing
        # here would discard it and re-read the still-PENDING row.
        assert report.decision == ReportDecision.CLOSED_ACCOUNT_DELETED
        assert report.decided_at is not None
        actions = {entry.action for entry in entries}
        assert AuditAction.DIRECT_MESSAGE_PRUNED in actions
        assert AuditAction.REPORT_DECIDED in actions

    def test_deleting_the_reporter_keeps_the_message_and_report_open(self, db_session):
        """spec's 'נמחקת המדווחת' — the message's recipient filed the report."""
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        message = _make_message(db_session, sender, recipient, "תוכן", datetime.now())
        report = _report(db_session, recipient, message, ReportDecision.PENDING)

        result, entries = retention_service.purge_user_direct_messages(
            db_session, recipient
        )

        assert result["deleted_message_ids"] == []
        assert result["closed_report_ids"] == []
        assert entries == []
        assert (
            db_session.query(DirectMessage)
            .filter(DirectMessage.id == message.id)
            .first()
        )
        assert report.decision == ReportDecision.PENDING

    def test_a_decided_report_does_not_block_deletion(self, db_session):
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        message = _make_message(db_session, sender, recipient, "תוכן", datetime.now())
        _report(db_session, recipient, message, ReportDecision.INVALID)

        result, _ = retention_service.purge_user_direct_messages(db_session, recipient)

        assert result["deleted_message_ids"] == [message.id]
        assert db_session.query(DirectMessage).count() == 0


# ---------------------------------------------------------------------------
# user_service.delete_own_account() — the full account-deletion flow
# ---------------------------------------------------------------------------


class TestDeleteOwnAccount:
    def test_scrubs_pii_and_cancels_the_account(self, db_session):
        user = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        user.phone = "0501234567"
        db_session.commit()
        original_id = user.id

        user_service.delete_own_account(db_session, user)

        db_session.refresh(user)
        assert user.id == original_id
        assert user.account_status == AccountStatus.CANCELLED
        assert user.phone is None
        assert user.email != "a@example.com"
        assert "@" in user.email

    def test_deletes_messages_and_logs_a_single_audit_entry_for_the_account(
        self, db_session
    ):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _make_message(db_session, a, b, "תוכן", datetime.now())

        user_service.delete_own_account(db_session, a)

        assert db_session.query(DirectMessage).count() == 0
        cancelled_entry = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.entity_id == a.id,
                AuditLog.action == AuditAction.USER_CANCELLED,
            )
            .first()
        )
        assert cancelled_entry is not None
        assert cancelled_entry.details["deleted_message_count"] == 1

    def test_cannot_delete_an_already_cancelled_account(self, db_session):
        user = _make_user(
            db_session,
            "a@example.com",
            account_status=AccountStatus.CANCELLED,
        )

        with pytest.raises(HTTPException) as exc_info:
            user_service.delete_own_account(db_session, user)
        assert exc_info.value.status_code == 400

    def test_moderator_deletion_clears_cells_and_alert_email(self, db_session):
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        moderator.moderator_cells = [{"group": "widow", "sector": "hasidic"}]
        moderator.alert_email = "alerts@example.com"
        db_session.commit()

        user_service.delete_own_account(db_session, moderator)

        db_session.refresh(moderator)
        assert moderator.moderator_cells == []
        assert moderator.alert_email is None

    def test_the_reporter_deleting_her_account_leaves_the_report_open_and_anonymous(
        self, db_session
    ):
        """
        End-to-end version of the 'נמחקת המדווחת' case: after deletion the
        report still resolves to a real row, but that row carries no more PII.
        """
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        message = _make_message(db_session, sender, recipient, "תוכן", datetime.now())
        report = _report(db_session, recipient, message, ReportDecision.PENDING)

        user_service.delete_own_account(db_session, recipient)

        db_session.refresh(report)
        assert report.decision == ReportDecision.PENDING
        reporter = db_session.query(User).filter(User.id == report.reporter_id).first()
        assert reporter.account_status == AccountStatus.CANCELLED
        assert reporter.email != "b@example.com"


# ---------------------------------------------------------------------------
# export_user_direct_messages()
# ---------------------------------------------------------------------------


class TestExportUserDirectMessages:
    def test_returns_only_the_callers_messages_decrypted(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        c = _make_user(db_session, "c@example.com", UserType.WIDOW, Sector.HASIDIC)
        _make_message(db_session, a, b, "שלום ל-b", datetime(2026, 1, 1))
        _make_message(db_session, b, a, "תשובה מ-b", datetime(2026, 1, 2))
        _make_message(db_session, b, c, "לא של a", datetime(2026, 1, 3))

        export = retention_service.export_user_direct_messages(db_session, a)

        assert [m["content"] for m in export] == ["שלום ל-b", "תשובה מ-b"]

    def test_empty_when_the_user_has_no_messages(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)

        assert retention_service.export_user_direct_messages(db_session, a) == []


# ---------------------------------------------------------------------------
# DELETE /users/me
# ---------------------------------------------------------------------------


class TestDeleteMyAccountEndpoint:
    async def test_deletes_own_account(self, client, db_session):
        user = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        _login_as(user)

        response = await client.delete(DELETE_ACCOUNT_URL)

        assert response.status_code == 204
        db_session.refresh(user)
        assert user.account_status == AccountStatus.CANCELLED

    async def test_deleting_twice_is_rejected(self, client, db_session):
        user = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        _login_as(user)

        await client.delete(DELETE_ACCOUNT_URL)
        response = await client.delete(DELETE_ACCOUNT_URL)

        assert response.status_code == 400

    async def test_unauthenticated_returns_401(self, client):
        """§3.2 negative permission check: no session at all, not just the wrong role."""
        response = await client.delete(DELETE_ACCOUNT_URL)

        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /users/me/messages/export
# ---------------------------------------------------------------------------


class TestExportMyMessagesEndpoint:
    async def test_user_can_export_own_messages(self, client, db_session):
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        other = _make_user(
            db_session, "other@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _make_message(db_session, me, other, "שלום", datetime(2026, 1, 1))
        _login_as(me)

        response = await client.get(MESSAGES_EXPORT_URL)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["content"] == "שלום"

    async def test_moderator_cannot_export(self, client, db_session):
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        _login_as(moderator)

        response = await client.get(MESSAGES_EXPORT_URL)

        assert response.status_code == 403

    async def test_admin_cannot_export(self, client, db_session):
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        _login_as(admin)

        response = await client.get(MESSAGES_EXPORT_URL)

        assert response.status_code == 403

    async def test_professional_cannot_export(self, client, db_session):
        professional = _make_user(
            db_session, "pro@example.com", role=UserRole.PROFESSIONAL
        )
        _login_as(professional)

        response = await client.get(MESSAGES_EXPORT_URL)

        assert response.status_code == 403
