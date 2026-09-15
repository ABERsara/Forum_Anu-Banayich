"""
Integration tests for the moderator's review of a DIRECT_MESSAGE report
(ABF-113): the pending/history lists, a single report's decrypted content,
the decision it leads to, and the audit trail behind both.

Straight API calls throughout (§4.2), not the service layer directly —
these are the endpoints a browser actually calls, and a permission check
that only ever ran against report_service.py could pass while the router
above it still leaked something.
"""

import pytest

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
from app.main import app
from app.models.audit import AuditLog
from app.models.forum import DirectMessage
from app.models.report import Report
from app.models.user import User
from app.schemas.forum import DirectMessageCreate
from app.schemas.report import ReportCreate
from app.services import forum_service, report_service

BASE = "/api/v1/moderator"
CELL = {"group": UserType.WIDOWER, "sector": Sector.HASIDIC}
OTHER_CELL = {"group": UserType.WIDOW, "sector": Sector.SEPHARDIC}


@pytest.fixture
def as_user():
    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


def _pair(db_session, make_user) -> tuple[User, User]:
    """A sender and recipient sharing CELL — a receivable, reportable message."""
    sender = make_user(
        "sender@example.com",
        user_type=UserType.WIDOWER,
        sector=Sector.HASIDIC,
        account_status=AccountStatus.ACTIVE,
    )
    recipient = make_user(
        "recipient@example.com",
        user_type=UserType.WIDOWER,
        sector=Sector.HASIDIC,
        account_status=AccountStatus.ACTIVE,
    )
    return sender, recipient


def _send_message(
    db_session, sender: User, recipient: User, content: str
) -> DirectMessage:
    result = forum_service.send_direct_message(
        db_session,
        DirectMessageCreate(recipient_id=recipient.id, content=content),
        sender,
    )
    return (
        db_session.query(DirectMessage)
        .filter(DirectMessage.id == result["message"]["id"])
        .one()
    )


def _file_dm_report(db_session, message: DirectMessage, reporter: User) -> Report:
    return report_service.file_report(
        db_session,
        ReportCreate(
            target_type=ReportTargetType.DIRECT_MESSAGE,
            target_id=message.id,
            reason=ReportReason.HARASSMENT,
        ),
        reporter,
    )


def _make_moderator(db_session, make_user) -> User:
    moderator = make_user("mod@example.com", role=UserRole.MODERATOR)
    moderator.moderator_cells = [CELL]
    db_session.commit()
    return moderator


def _make_outside_moderator(db_session, make_user) -> User:
    moderator = make_user("outside-mod@example.com", role=UserRole.MODERATOR)
    moderator.moderator_cells = [OTHER_CELL]
    db_session.commit()
    return moderator


def _decide_body(decision: ReportDecision, note: str = "נבדק מול כללי הקהילה") -> dict:
    return {"decision": decision.value, "note": note}


# ---------------------------------------------------------------------------
# GET /moderator/reports — a DIRECT_MESSAGE report in the pending queue
# ---------------------------------------------------------------------------


class TestPendingListIncludesDirectMessageReports:
    async def test_moderator_sees_dm_report_in_matching_cell(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן רגיש")
        report = _file_dm_report(db_session, message, recipient)

        response = await client.get(f"{BASE}/reports")

        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["items"]]
        assert report.id in ids

    async def test_moderator_outside_cell_does_not_see_it(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_outside_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן רגיש")
        _file_dm_report(db_session, message, recipient)

        response = await client.get(f"{BASE}/reports")

        assert response.json()["items"] == []

    async def test_list_does_not_expose_decrypted_content(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(
            db_session, sender, recipient, "תוכן סודי שלא אמור להופיע"
        )
        _file_dm_report(db_session, message, recipient)

        response = await client.get(f"{BASE}/reports")

        assert "תוכן סודי" not in response.text
        assert response.json()["items"][0].get("message_content") is None


# ---------------------------------------------------------------------------
# GET /moderator/reports/{id} — the audited, decrypted single view
# ---------------------------------------------------------------------------


class TestGetSingleDirectMessageReport:
    async def test_moderator_in_cell_gets_decrypted_content(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן ההודעה שדווחה")
        report = _file_dm_report(db_session, message, recipient)

        response = await client.get(f"{BASE}/reports/{report.id}")

        assert response.status_code == 200
        assert response.json()["message_content"] == "תוכן ההודעה שדווחה"

    async def test_moderator_outside_cell_gets_403(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_outside_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן")
        report = _file_dm_report(db_session, message, recipient)

        response = await client.get(f"{BASE}/reports/{report.id}")

        assert response.status_code == 403

    async def test_admin_can_view_regardless_of_cell(
        self, client, make_user, as_user, db_session
    ):
        as_user(make_user("admin@example.com", role=UserRole.ADMIN))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן")
        report = _file_dm_report(db_session, message, recipient)

        response = await client.get(f"{BASE}/reports/{report.id}")

        assert response.status_code == 200
        assert response.json()["message_content"] == "תוכן"

    async def test_viewing_writes_exactly_one_audit_entry_naming_no_text(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן חסוי במיוחד")
        report = _file_dm_report(db_session, message, recipient)

        await client.get(f"{BASE}/reports/{report.id}")

        entries = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_REPORT_VIEWED)
            .all()
        )
        assert len(entries) == 1
        assert entries[0].entity_id == report.id
        assert "תוכן חסוי" not in str(entries[0].details)

    async def test_denied_access_is_also_audited(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_outside_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן")
        report = _file_dm_report(db_session, message, recipient)

        response = await client.get(f"{BASE}/reports/{report.id}")

        assert response.status_code == 403
        entries = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_ACCESS_DENIED)
            .all()
        )
        assert len(entries) == 1
        assert entries[0].entity_id == report.id


# ---------------------------------------------------------------------------
# POST /moderator/reports/{id}/decide
# ---------------------------------------------------------------------------


class TestDecideDirectMessageReport:
    async def test_valid_hides_the_message(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן")
        report = _file_dm_report(db_session, message, recipient)

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.VALID),
        )

        assert response.status_code == 200
        db_session.refresh(message)
        assert message.hidden_at is not None

    async def test_invalid_leaves_the_message_untouched(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן")
        report = _file_dm_report(db_session, message, recipient)

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.INVALID),
        )

        assert response.status_code == 200
        db_session.refresh(message)
        assert message.hidden_at is None

    async def test_decided_report_cannot_be_decided_again(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן")
        report = _file_dm_report(db_session, message, recipient)
        await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.VALID),
        )

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.INVALID),
        )

        assert response.status_code == 409

    async def test_denied_decide_is_audited_as_a_decide_attempt_not_a_view(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_outside_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן")
        report = _file_dm_report(db_session, message, recipient)

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.VALID),
        )

        assert response.status_code == 403
        entries = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_ACCESS_DENIED)
            .all()
        )
        assert len(entries) == 1
        assert entries[0].entity_id == report.id
        assert entries[0].details["context"] == "moderator_report_decide"


# ---------------------------------------------------------------------------
# A report closed by account deletion (spec §9.4, "הכרעה ו'") — already
# produced by retention_service.purge_user_direct_messages() (ABF-117); these
# pin what the moderator-facing endpoints do with a report already in that
# state, not the deletion flow itself.
# ---------------------------------------------------------------------------


class TestClosedAccountDeletedReport:
    async def test_cannot_be_decided(self, client, make_user, as_user, db_session):
        as_user(_make_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן")
        report = _file_dm_report(db_session, message, recipient)
        report.decision = ReportDecision.CLOSED_ACCOUNT_DELETED
        db_session.commit()

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.VALID),
        )

        assert response.status_code == 409

    async def test_content_not_exposed_even_to_the_covering_moderator(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_moderator(db_session, make_user))
        sender, recipient = _pair(db_session, make_user)
        message = _send_message(db_session, sender, recipient, "תוכן שלא אמור להיחשף")
        report = _file_dm_report(db_session, message, recipient)
        report.decision = ReportDecision.CLOSED_ACCOUNT_DELETED
        db_session.commit()

        response = await client.get(f"{BASE}/reports/{report.id}")

        assert response.status_code == 200
        assert response.json()["message_content"] is None


# ---------------------------------------------------------------------------
# §3.2/§4.2 — roles with no report-handling permission at all
# ---------------------------------------------------------------------------


class TestPermissionMatrix:
    async def test_user_role_forbidden(self, client, make_user, as_user):
        as_user(make_user("user@example.com", role=UserRole.USER))

        response = await client.get(f"{BASE}/reports")

        assert response.status_code == 403

    async def test_professional_role_forbidden(self, client, make_user, as_user):
        as_user(make_user("pro@example.com", role=UserRole.PROFESSIONAL))

        response = await client.get(f"{BASE}/reports")

        assert response.status_code == 403
