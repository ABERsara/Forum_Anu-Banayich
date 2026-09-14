"""
Reporting a private message (ABF-112).

The acceptance criteria this file pins, in the order the ticket lists them:

  * a report cannot be filed without a reason - enforced by the API, not only
    by the dialog (TestReportEndpointValidation);
  * the record holds exactly one message (TestSnapshotHoldsOneMessage);
  * that snapshot is encrypted at rest (TestSnapshotIsEncrypted);
  * reaching an adjacent message from the report is refused with 403
    (TestAdjacentMessageAccess);
  * forum reporting is unchanged (TestForumReportsUnaffected, plus the whole
    of test_report_service.py);
  * the frozen schema carries the closing status and an anonymizable reporter
    id (TestFrozenReportSchema).

Plus the DoD's own: permission checks made straight against the API rather
than through any UI (§4.2), a denial that does not reveal whether a user or a
conversation exists, an audit entry for opening private content to a
moderator (§9.3), and no message text anywhere in the logs.
"""

import inspect
import logging

import pytest
from fastapi import HTTPException

from app.core.constants import (
    AccountStatus,
    AuditAction,
    GroupVisibility,
    ReportDecision,
    ReportReason,
    ReportTargetType,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_active_user, get_current_user
from app.core.encryption import decrypt_message
from app.core.messages import HEBREW, MESSAGES
from app.main import app
from app.models.audit import AuditLog
from app.models.forum import DirectMessage, ForumPost
from app.models.report import Report
from app.models.user import User
from app.schemas.forum import DirectMessageCreate
from app.schemas.report import ReportCreate
from app.services import forum_service, report_service
from app.services.email_service import send_direct_message_report_alert

MESSAGES_BASE = "/api/v1/messages"
CONVERSATIONS_BASE = "/api/v1/conversations"

CELL = {"group": UserType.WIDOW.value, "sector": Sector.HASIDIC.value}


def _make_user(
    db_session,
    email: str,
    user_type: UserType | None = UserType.WIDOW,
    sector: Sector | None = Sector.HASIDIC,
    role: UserRole = UserRole.USER,
    alert_email: str | None = None,
    moderator_cells: list[dict[str, str]] | None = None,
) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        user_type=user_type,
        sector=sector,
        account_status=AccountStatus.ACTIVE,
        alert_email=alert_email,
        moderator_cells=moderator_cells,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login_as(user: User) -> None:
    """Bypass real JWT auth, same technique as test_direct_messages.py."""
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_active_user] = lambda: user


def _send(db_session, sender: User, recipient: User, content: str) -> DirectMessage:
    """Send one message through the service and return the stored row."""
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


def _report_body(target_id: str, reason: str = ReportReason.HARASSMENT.value) -> dict:
    return {
        "target_type": ReportTargetType.DIRECT_MESSAGE.value,
        "target_id": target_id,
        "reason": reason,
    }


def _report_data(target_id: str) -> ReportCreate:
    return ReportCreate(
        target_type=ReportTargetType.DIRECT_MESSAGE,
        target_id=target_id,
        reason=ReportReason.HARASSMENT,
    )


@pytest.fixture
def pair(db_session):
    """A sender and the cell-mate who receives (and reports) her messages."""
    sender = _make_user(db_session, "sender@example.com")
    recipient = _make_user(db_session, "recipient@example.com")
    return sender, recipient


# ---------------------------------------------------------------------------
# The record holds exactly one message
# ---------------------------------------------------------------------------


class TestSnapshotHoldsOneMessage:
    def test_one_report_row_naming_the_reported_message(self, db_session, pair):
        sender, recipient = pair
        _send(db_session, sender, recipient, "הודעה קודמת")
        reported = _send(db_session, sender, recipient, "ההודעה הפוגענית")
        _send(db_session, sender, recipient, "הודעה שאחריה")

        report = report_service.file_report(
            db_session, _report_data(reported.id), recipient
        )

        assert db_session.query(Report).count() == 1
        assert report.target_id == reported.id
        assert report.target_type == ReportTargetType.DIRECT_MESSAGE
        assert report.reporter_id == recipient.id
        assert report.reported_user_id == sender.id
        assert report.decision == ReportDecision.PENDING

    def test_snapshot_is_the_reported_message_and_not_its_neighbours(
        self, db_session, pair
    ):
        sender, recipient = pair
        _send(db_session, sender, recipient, "לפני")
        reported = _send(db_session, sender, recipient, "ההודעה שדווחה")
        _send(db_session, sender, recipient, "אחרי")

        report = report_service.file_report(
            db_session, _report_data(reported.id), recipient
        )

        assert (
            decrypt_message(
                report.reported_content, report.reported_content_key_version
            )
            == "ההודעה שדווחה"
        )

    def test_report_carries_no_handle_to_the_rest_of_the_conversation(
        self, db_session, pair
    ):
        """
        The structural half of "one message only": nothing on the report row
        names the conversation, so holding a report is not a way to ask for
        what came before or after it.
        """
        sender, recipient = pair
        reported = _send(db_session, sender, recipient, "טקסט")

        report = report_service.file_report(
            db_session, _report_data(reported.id), recipient
        )

        columns = {column.name for column in Report.__table__.columns}
        assert "conversation_key" not in columns
        stored = {value for value in vars(report).values() if isinstance(value, str)}
        assert reported.conversation_key not in stored


# ---------------------------------------------------------------------------
# The snapshot is encrypted at rest
# ---------------------------------------------------------------------------


class TestSnapshotIsEncrypted:
    def test_plaintext_is_not_in_the_stored_column(self, db_session, pair):
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "תוכן פוגעני מאוד")

        report = report_service.file_report(
            db_session, _report_data(message.id), recipient
        )

        assert report.reported_content is not None
        assert "תוכן פוגעני מאוד" not in report.reported_content
        assert (
            decrypt_message(
                report.reported_content, report.reported_content_key_version
            )
            == "תוכן פוגעני מאוד"
        )

    def test_raw_sql_read_of_the_row_shows_ciphertext(self, db_session, pair):
        """
        Read back the way anything with database access would read it - the
        column itself, not the ORM object - because "encrypted in the DB" is a
        claim about what is on disk.
        """
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "סוד")
        report = report_service.file_report(
            db_session, _report_data(message.id), recipient
        )

        stored = (
            db_session.query(Report.reported_content)
            .filter(Report.id == report.id)
            .scalar()
        )

        assert stored != "סוד"
        assert "סוד" not in stored

    def test_snapshot_reuses_the_message_ciphertext_verbatim(self, db_session, pair):
        """
        Copied, not decrypted and re-encrypted: it is the same bytes under the
        same key epoch, which is what keeps the plaintext out of the process
        while a report is filed.
        """
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "טקסט")
        stored_ciphertext, key_version = message.content, message.key_version

        report = report_service.file_report(
            db_session, _report_data(message.id), recipient
        )

        assert report.reported_content == stored_ciphertext
        assert report.reported_content_key_version == key_version


# ---------------------------------------------------------------------------
# Who may file one - §4.2, straight at the API
# ---------------------------------------------------------------------------


class TestReportEndpointPermissions:
    async def test_recipient_can_report_a_message_she_received(
        self, client, db_session, pair
    ):
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "הודעה")
        _login_as(recipient)

        r = await client.post(
            f"{MESSAGES_BASE}/{message.id}/report", json=_report_body(message.id)
        )

        assert r.status_code == 201
        body = r.json()
        assert body["target_id"] == message.id
        assert body["reported_user_id"] == sender.id
        assert body["decision"] == ReportDecision.PENDING.value
        # The report the client gets back never carries the snapshot.
        assert "reported_content" not in body

    async def test_sender_cannot_report_her_own_message(self, client, db_session, pair):
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "הודעה")
        _login_as(sender)

        r = await client.post(
            f"{MESSAGES_BASE}/{message.id}/report", json=_report_body(message.id)
        )

        assert r.status_code == 403
        assert r.json()["detail"] == "errors.dm_forbidden"
        assert db_session.query(Report).count() == 0

    async def test_third_party_in_the_same_cell_is_refused(
        self, client, db_session, pair
    ):
        sender, recipient = pair
        outsider = _make_user(db_session, "outsider@example.com")
        message = _send(db_session, sender, recipient, "הודעה")
        _login_as(outsider)

        r = await client.post(
            f"{MESSAGES_BASE}/{message.id}/report", json=_report_body(message.id)
        )

        assert r.status_code == 403
        assert db_session.query(Report).count() == 0

    async def test_moderator_cannot_file_one_on_a_conversation(
        self, client, db_session, pair
    ):
        """
        §5.3: a moderator sees a private message because a user handed it to
        her, never by reaching for it - including through this route.
        """
        sender, recipient = pair
        moderator = _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[CELL],
        )
        message = _send(db_session, sender, recipient, "הודעה")
        _login_as(moderator)

        r = await client.post(
            f"{MESSAGES_BASE}/{message.id}/report", json=_report_body(message.id)
        )

        assert r.status_code == 403
        assert db_session.query(Report).count() == 0

    async def test_unknown_message_id_is_refused_exactly_like_someone_elses(
        self, client, db_session, pair
    ):
        """
        The non-leaking rule: an id that never existed and an id belonging to
        a conversation the caller is not in must be answered identically, or
        the difference becomes a way to enumerate messages.
        """
        sender, recipient = pair
        outsider = _make_user(db_session, "outsider@example.com")
        real = _send(db_session, sender, recipient, "הודעה")
        _login_as(outsider)

        unknown = await client.post(
            f"{MESSAGES_BASE}/does-not-exist/report",
            json=_report_body("does-not-exist"),
        )
        someone_elses = await client.post(
            f"{MESSAGES_BASE}/{real.id}/report", json=_report_body(real.id)
        )

        assert unknown.status_code == someone_elses.status_code == 403
        assert unknown.json() == someone_elses.json()


# ---------------------------------------------------------------------------
# A report needs a reason, and a target that matches the route
# ---------------------------------------------------------------------------


class TestReportEndpointValidation:
    async def test_missing_reason_is_rejected(self, client, db_session, pair):
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "הודעה")
        _login_as(recipient)

        r = await client.post(
            f"{MESSAGES_BASE}/{message.id}/report",
            json={
                "target_type": ReportTargetType.DIRECT_MESSAGE.value,
                "target_id": message.id,
            },
        )

        assert r.status_code == 422
        assert db_session.query(Report).count() == 0

    async def test_empty_reason_is_rejected(self, client, db_session, pair):
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "הודעה")
        _login_as(recipient)

        r = await client.post(
            f"{MESSAGES_BASE}/{message.id}/report", json=_report_body(message.id, "")
        )

        assert r.status_code == 422
        assert db_session.query(Report).count() == 0

    async def test_body_naming_another_message_is_rejected(
        self, client, db_session, pair
    ):
        sender, recipient = pair
        first = _send(db_session, sender, recipient, "ראשונה")
        second = _send(db_session, sender, recipient, "שנייה")
        _login_as(recipient)

        r = await client.post(
            f"{MESSAGES_BASE}/{first.id}/report", json=_report_body(second.id)
        )

        assert r.status_code == 400
        assert r.json()["detail"] == MESSAGES["reports.payload_mismatch"][HEBREW]
        assert db_session.query(Report).count() == 0

    async def test_body_claiming_a_forum_post_is_rejected(
        self, client, db_session, pair
    ):
        """
        A FORUM_POST body on this route would otherwise be dispatched to the
        forum path and answered 404 by a post lookup - a reply about forum
        posts to a question about a private message.
        """
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "הודעה")
        _login_as(recipient)

        r = await client.post(
            f"{MESSAGES_BASE}/{message.id}/report",
            json={
                "target_type": ReportTargetType.FORUM_POST.value,
                "target_id": message.id,
                "reason": ReportReason.SPAM.value,
            },
        )

        assert r.status_code == 400
        assert db_session.query(Report).count() == 0


# ---------------------------------------------------------------------------
# §7.1 step 4 - one report per user per message
# ---------------------------------------------------------------------------


class TestDuplicateReports:
    async def test_second_report_on_the_same_message_is_refused(
        self, client, db_session, pair
    ):
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "הודעה")
        _login_as(recipient)

        first = await client.post(
            f"{MESSAGES_BASE}/{message.id}/report", json=_report_body(message.id)
        )
        second = await client.post(
            f"{MESSAGES_BASE}/{message.id}/report",
            json=_report_body(message.id, ReportReason.SPAM.value),
        )

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["detail"] == MESSAGES["reports.already_reported"][HEBREW]
        assert db_session.query(Report).count() == 1

    def test_a_second_message_from_the_same_sender_can_still_be_reported(
        self, db_session, pair
    ):
        """The block is per message, not per sender."""
        sender, recipient = pair
        first = _send(db_session, sender, recipient, "ראשונה")
        second = _send(db_session, sender, recipient, "שנייה")

        report_service.file_report(db_session, _report_data(first.id), recipient)
        report_service.file_report(db_session, _report_data(second.id), recipient)

        assert db_session.query(Report).count() == 2


# ---------------------------------------------------------------------------
# Reaching the neighbours of a reported message
# ---------------------------------------------------------------------------


class TestAdjacentMessageAccess:
    async def test_moderator_cannot_read_the_conversation_the_report_came_from(
        self, client, db_session, pair
    ):
        sender, recipient = pair
        _send(db_session, sender, recipient, "ההודעה שלפני")
        reported = _send(db_session, sender, recipient, "ההודעה שדווחה")
        moderator = _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[CELL],
        )
        report_service.file_report(db_session, _report_data(reported.id), recipient)
        _login_as(moderator)

        r = await client.get(
            f"{CONVERSATIONS_BASE}/{reported.conversation_key}/messages"
        )

        assert r.status_code == 403
        assert r.json()["detail"] == "errors.dm_forbidden"

    async def test_a_denied_neighbour_read_is_audited(self, client, db_session, pair):
        sender, recipient = pair
        reported = _send(db_session, sender, recipient, "ההודעה שדווחה")
        moderator = _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[CELL],
        )
        report_service.file_report(db_session, _report_data(reported.id), recipient)
        _login_as(moderator)

        await client.get(f"{CONVERSATIONS_BASE}/{reported.conversation_key}/messages")

        denials = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_ACCESS_DENIED)
            .all()
        )
        assert [entry.actor_id for entry in denials] == [moderator.id]

    async def test_reporter_cannot_report_a_message_she_sent_in_the_same_thread(
        self, client, db_session, pair
    ):
        """
        Reporting one message does not open the thread: the reporter's own
        message next to it is still not hers to act on through this route.
        """
        sender, recipient = pair
        reported = _send(db_session, sender, recipient, "שלה")
        mine = _send(db_session, recipient, sender, "שלי")
        report_service.file_report(db_session, _report_data(reported.id), recipient)
        _login_as(recipient)

        r = await client.post(
            f"{MESSAGES_BASE}/{mine.id}/report", json=_report_body(mine.id)
        )

        assert r.status_code == 403
        assert db_session.query(Report).count() == 1


# ---------------------------------------------------------------------------
# §9.3 audit, and the "no content in the logs" rule
# ---------------------------------------------------------------------------


class TestAuditTrail:
    def test_filing_writes_one_entry_naming_the_message(self, db_session, pair):
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "תוכן רגיש")

        report = report_service.file_report(
            db_session, _report_data(message.id), recipient
        )

        entries = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_REPORTED)
            .all()
        )
        assert len(entries) == 1
        entry = entries[0]
        assert entry.actor_id == recipient.id
        assert entry.entity_type == "DirectMessage"
        assert entry.entity_id == message.id
        assert entry.details == {
            "report_id": report.id,
            "reason": ReportReason.HARASSMENT.value,
        }

    def test_the_audit_entry_carries_no_message_text(self, db_session, pair):
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "תוכן רגיש")

        report_service.file_report(db_session, _report_data(message.id), recipient)

        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_REPORTED)
            .one()
        )
        assert "תוכן רגיש" not in str(entry.details)

    def test_a_refused_attempt_is_audited_and_files_nothing(self, db_session, pair):
        sender, recipient = pair
        outsider = _make_user(db_session, "outsider@example.com")
        message = _send(db_session, sender, recipient, "הודעה")

        with pytest.raises(HTTPException) as exc_info:
            report_service.file_report(db_session, _report_data(message.id), outsider)

        assert exc_info.value.status_code == 403
        assert db_session.query(Report).count() == 0
        denied = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_ACCESS_DENIED)
            .one()
        )
        assert denied.actor_id == outsider.id
        assert denied.entity_id == message.id

    def test_no_message_text_reaches_the_logs(self, db_session, pair, caplog):
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "מילות התוכן הפוגעני")

        with caplog.at_level(logging.DEBUG):
            report_service.file_report(db_session, _report_data(message.id), recipient)

        assert "מילות התוכן הפוגעני" not in caplog.text


# ---------------------------------------------------------------------------
# §7.1 step 5 - routing the alert
# ---------------------------------------------------------------------------


class TestModeratorRouting:
    def test_alert_goes_to_the_moderator_of_the_senders_cell(
        self, db_session, pair, monkeypatch
    ):
        sender, recipient = pair
        _make_user(
            db_session,
            "responsible@example.com",
            role=UserRole.MODERATOR,
            alert_email="alerts@example.com",
            moderator_cells=[CELL],
        )
        message = _send(db_session, sender, recipient, "הודעה")
        sent: list[tuple[str, str]] = []
        monkeypatch.setattr(
            report_service,
            "send_direct_message_report_alert",
            lambda email, report_id: sent.append((email, report_id)),
        )

        report = report_service.file_report(
            db_session, _report_data(message.id), recipient
        )

        assert sent == [("alerts@example.com", report.id)]

    def test_a_moderator_of_another_cell_is_not_told(
        self, db_session, pair, monkeypatch
    ):
        sender, recipient = pair
        _make_user(
            db_session,
            "elsewhere@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[
                {"group": UserType.ORPHAN_MALE.value, "sector": Sector.LITVISH.value}
            ],
        )
        message = _send(db_session, sender, recipient, "הודעה")
        sent: list[str] = []
        monkeypatch.setattr(
            report_service,
            "send_direct_message_report_alert",
            lambda email, report_id: sent.append(email),
        )

        report_service.file_report(db_session, _report_data(message.id), recipient)

        assert sent == []

    def test_the_alert_signature_cannot_carry_the_message(self):
        """
        The email stub takes an id and nothing else - the guarantee that a
        private message is never mailed out lives in the signature, not in the
        discipline of its callers.
        """
        params = inspect.signature(send_direct_message_report_alert).parameters

        assert list(params) == ["moderator_email", "report_id"]

    def test_a_failed_alert_does_not_undo_the_report(
        self, db_session, pair, monkeypatch
    ):
        sender, recipient = pair
        _make_user(
            db_session,
            "responsible@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[CELL],
        )
        message = _send(db_session, sender, recipient, "הודעה")

        def _boom(email: str, report_id: str) -> None:
            raise RuntimeError("smtp down")

        monkeypatch.setattr(report_service, "send_direct_message_report_alert", _boom)

        report = report_service.file_report(
            db_session, _report_data(message.id), recipient
        )

        assert db_session.query(Report).filter(Report.id == report.id).one()


# ---------------------------------------------------------------------------
# Marking the message as reported, for the screen
# ---------------------------------------------------------------------------


class TestReportedMarkerOnTheConversation:
    async def test_only_the_reported_message_comes_back_marked(
        self, client, db_session, pair
    ):
        sender, recipient = pair
        before = _send(db_session, sender, recipient, "לפני")
        reported = _send(db_session, sender, recipient, "שדווחה")
        after = _send(db_session, sender, recipient, "אחרי")
        report_service.file_report(db_session, _report_data(reported.id), recipient)
        _login_as(recipient)

        r = await client.get(
            f"{CONVERSATIONS_BASE}/{reported.conversation_key}/messages"
        )

        assert r.status_code == 200
        marks = {item["id"]: item["reported_by_me"] for item in r.json()["items"]}
        assert marks == {before.id: False, reported.id: True, after.id: False}

    async def test_the_sender_does_not_see_her_message_marked(
        self, client, db_session, pair
    ):
        """
        The marker answers "did *I* report this", so it must not become a way
        for a sender to learn she was reported.
        """
        sender, recipient = pair
        reported = _send(db_session, sender, recipient, "שדווחה")
        report_service.file_report(db_session, _report_data(reported.id), recipient)
        _login_as(sender)

        r = await client.get(
            f"{CONVERSATIONS_BASE}/{reported.conversation_key}/messages"
        )

        assert r.status_code == 200
        assert [item["reported_by_me"] for item in r.json()["items"]] == [False]

    async def test_a_sent_message_comes_back_unmarked(self, client, db_session, pair):
        sender, recipient = pair
        _login_as(sender)

        r = await client.post(
            MESSAGES_BASE, json={"recipient_id": recipient.id, "content": "שלום"}
        )

        assert r.status_code == 201
        assert r.json()["message"]["reported_by_me"] is False

    def test_the_marker_survives_a_decision(self, db_session, pair):
        """
        A ruled-on report is still a report this user filed. Un-marking the
        message once a moderator decides would invite her to file it again.
        """
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "שדווחה")
        report = report_service.file_report(
            db_session, _report_data(message.id), recipient
        )
        report.decision = ReportDecision.INVALID
        db_session.commit()

        page = forum_service.get_conversation_messages(
            db_session, recipient, message.conversation_key
        )

        assert [item["reported_by_me"] for item in page["items"]] == [True]


# ---------------------------------------------------------------------------
# Forum reporting is untouched
# ---------------------------------------------------------------------------


class TestForumReportsUnaffected:
    def test_a_forum_report_stores_no_snapshot(self, db_session):
        author = _make_user(db_session, "author@example.com")
        reporter = _make_user(db_session, "reporter@example.com")
        post = ForumPost(
            author_id=author.id,
            title="כותרת",
            content="תוכן",
            group_visibility=GroupVisibility.ALL,
            sector_visibility=SectorVisibility.ALL,
        )
        db_session.add(post)
        db_session.commit()

        report = report_service.file_report(
            db_session,
            ReportCreate(
                target_type=ReportTargetType.FORUM_POST,
                target_id=post.id,
                reason=ReportReason.SPAM,
            ),
            reporter,
        )

        assert report.reported_content is None
        assert report.reported_content_key_version is None
        db_session.refresh(post)
        assert post.report_count == 1


# ---------------------------------------------------------------------------
# The frozen schema tasks 6-8 build against
# ---------------------------------------------------------------------------


class TestFrozenReportSchema:
    def test_the_closing_status_exists(self):
        assert ReportDecision.CLOSED_ACCOUNT_DELETED.value == "closed_account_deleted"

    def test_a_report_can_be_stored_without_a_reporter(self, db_session, pair):
        """
        §9.4 keeps a report for five years and anonymizes it when the account
        closes. Task 8 owns that flow; this pins that the column it will write
        to accepts the absence.
        """
        sender, recipient = pair
        message = _send(db_session, sender, recipient, "הודעה")
        report = report_service.file_report(
            db_session, _report_data(message.id), recipient
        )

        report.reporter_id = None
        report.decision = ReportDecision.CLOSED_ACCOUNT_DELETED
        db_session.commit()
        db_session.refresh(report)

        assert report.reporter_id is None
        assert report.reporter is None
        assert report.decision == ReportDecision.CLOSED_ACCOUNT_DELETED
        # The evidence outlives the identity - that is the point of keeping it.
        assert report.reported_content is not None
