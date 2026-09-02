"""
Tests for private messaging between cell members (ABF-118) and the
conversations inbox built on top of it (ABF-119).

Two layers, matching test_forum_service.py / test_forum_endpoints.py:
  - TestCanMessage / TestSend* / TestGetConversationMessages / TestGetCellMembers /
    TestGetInbox exercise forum_service functions directly.
  - TestSendMessageEndpoint / TestGetConversationMessagesEndpoint /
    TestGetCellMembersEndpoint / TestGetInboxEndpoint go through the real HTTP
    routes, hitting the API directly rather than through any UI — required by
    §4.2's positive AND negative permission checks.
"""

from datetime import datetime

from sqlalchemy import event

from app.core.constants import AccountStatus, AuditAction, Sector, UserRole, UserType
from app.core.dependencies import get_current_active_user, get_current_user
from app.core.encryption import decrypt_message
from app.main import app
from app.models.audit import AuditLog
from app.models.forum import DirectMessage
from app.models.user import User
from app.schemas.forum import DirectMessageCreate
from app.services import forum_service

MESSAGES_BASE = "/api/v1/messages"
CONVERSATIONS_BASE = "/api/v1/conversations"
CELL_MEMBERS_URL = "/api/v1/cells/me/members"


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
    """Bypass real JWT auth, same technique as test_forum_endpoints.py."""
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_active_user] = lambda: user


# ---------------------------------------------------------------------------
# can_message() / build_conversation_key()
# ---------------------------------------------------------------------------


class TestCanMessage:
    def test_true_for_same_cell_active_users(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)

        assert forum_service.can_message(a, b) is True

    def test_false_for_different_group(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOWER, Sector.HASIDIC)

        assert forum_service.can_message(a, b) is False

    def test_false_for_different_sector(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.SEPHARDIC)

        assert forum_service.can_message(a, b) is False

    def test_false_when_recipient_not_active(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(
            db_session,
            "b@example.com",
            UserType.WIDOW,
            Sector.HASIDIC,
            account_status=AccountStatus.SUSPENDED,
        )

        assert forum_service.can_message(a, b) is False

    def test_false_when_recipient_is_moderator(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)

        assert forum_service.can_message(a, moderator) is False

    def test_false_when_sender_is_admin(self, db_session):
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)

        assert forum_service.can_message(admin, b) is False


class TestBuildConversationKey:
    def test_order_independent(self):
        assert forum_service.build_conversation_key(
            "id-1", "id-2"
        ) == forum_service.build_conversation_key("id-2", "id-1")


# ---------------------------------------------------------------------------
# send_direct_message()
# ---------------------------------------------------------------------------


class TestSendDirectMessage:
    def test_success_stores_encrypted_content(self, db_session):
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )

        result = forum_service.send_direct_message(
            db_session,
            DirectMessageCreate(recipient_id=recipient.id, content="שלום, מה שלומך?"),
            sender,
        )

        assert result["content"] == "שלום, מה שלומך?"

        row = (
            db_session.query(DirectMessage)
            .filter(DirectMessage.id == result["id"])
            .one()
        )
        assert row.content != "שלום, מה שלומך?"
        assert decrypt_message(row.content, row.key_version) == "שלום, מה שלומך?"
        assert row.conversation_key == forum_service.build_conversation_key(
            sender.id, recipient.id
        )

    def test_cross_cell_raises_403_and_logs_audit(self, db_session):
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        other_cell = _make_user(
            db_session, "b@example.com", UserType.WIDOWER, Sector.SEPHARDIC
        )

        try:
            forum_service.send_direct_message(
                db_session,
                DirectMessageCreate(recipient_id=other_cell.id, content="הי"),
                sender,
            )
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 403

        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_ACCESS_DENIED)
            .one()
        )
        assert entry.actor_id == sender.id

    def test_nonexistent_recipient_raises_same_403_as_wrong_cell(self, db_session):
        """Doesn't leak whether a user id exists — same status/detail either way."""
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        wrong_cell = _make_user(
            db_session, "b@example.com", UserType.WIDOWER, Sector.SEPHARDIC
        )

        def _send(recipient_id: str) -> tuple[int, str]:
            try:
                forum_service.send_direct_message(
                    db_session,
                    DirectMessageCreate(recipient_id=recipient_id, content="הי"),
                    sender,
                )
                raise AssertionError("expected HTTPException")
            except Exception as exc:
                return exc.status_code, exc.detail

        assert _send("no-such-user-id") == _send(wrong_cell.id)

    def test_moderator_cannot_send(self, db_session):
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )

        try:
            forum_service.send_direct_message(
                db_session,
                DirectMessageCreate(recipient_id=recipient.id, content="הי"),
                moderator,
            )
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403

    def test_professional_cannot_send(self, db_session):
        professional = _make_user(
            db_session, "prof@example.com", role=UserRole.PROFESSIONAL
        )
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )

        try:
            forum_service.send_direct_message(
                db_session,
                DirectMessageCreate(recipient_id=recipient.id, content="הי"),
                professional,
            )
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403

    def test_admin_cannot_send_via_regular_path(self, db_session):
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )

        try:
            forum_service.send_direct_message(
                db_session,
                DirectMessageCreate(recipient_id=recipient.id, content="הי"),
                admin,
            )
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403


# ---------------------------------------------------------------------------
# get_conversation_messages()
# ---------------------------------------------------------------------------


class TestGetConversationMessages:
    def test_returns_full_history_oldest_first(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="ראשונה"), a
        )
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=a.id, content="שנייה"), b
        )

        key = forum_service.build_conversation_key(a.id, b.id)
        results = forum_service.get_conversation_messages(db_session, a, key)

        assert [r["content"] for r in results] == ["ראשונה", "שנייה"]

    def test_does_not_mutate_is_read(self, db_session):
        """
        Pure read, no side effects — marking as read is
        mark_conversation_read()'s job, not this function's (ABF-119 code
        review: a get_* function silently writing was a footgun for future
        callers assuming it's a safe, idempotent read).
        """
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=a.id, content="הי"), b
        )
        key = forum_service.build_conversation_key(a.id, b.id)

        forum_service.get_conversation_messages(db_session, a, key)

        row = (
            db_session.query(DirectMessage)
            .filter(DirectMessage.sender_id == b.id)
            .one()
        )
        assert row.is_read is False

    def test_well_formed_key_with_no_messages_returns_empty_list(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)

        key = forum_service.build_conversation_key(a.id, b.id)
        results = forum_service.get_conversation_messages(db_session, a, key)

        assert results == []

    def test_non_participant_raises_403_and_logs_audit(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        snooper = _make_user(
            db_session, "c@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        key = forum_service.build_conversation_key(a.id, b.id)

        try:
            forum_service.get_conversation_messages(db_session, snooper, key)
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403

        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_ACCESS_DENIED)
            .one()
        )
        assert entry.actor_id == snooper.id

    def test_legitimate_read_does_not_create_audit_entry(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="הי"), a
        )

        key = forum_service.build_conversation_key(a.id, b.id)
        forum_service.get_conversation_messages(db_session, a, key)

        assert db_session.query(AuditLog).count() == 0

    def test_moderator_cannot_read(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        key = forum_service.build_conversation_key(a.id, b.id)

        try:
            forum_service.get_conversation_messages(db_session, moderator, key)
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403

    def test_admin_cannot_read(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        key = forum_service.build_conversation_key(a.id, b.id)

        try:
            forum_service.get_conversation_messages(db_session, admin, key)
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403


# ---------------------------------------------------------------------------
# mark_conversation_read()
# ---------------------------------------------------------------------------


class TestMarkConversationRead:
    def test_marks_received_messages_as_read_but_not_sent_ones(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="מאה לבי"), a
        )
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=a.id, content="מבי לאה"), b
        )
        key = forum_service.build_conversation_key(a.id, b.id)

        forum_service.mark_conversation_read(db_session, a, key)

        sent_to_a = (
            db_session.query(DirectMessage)
            .filter(DirectMessage.sender_id == b.id, DirectMessage.recipient_id == a.id)
            .one()
        )
        sent_by_a = (
            db_session.query(DirectMessage)
            .filter(DirectMessage.sender_id == a.id, DirectMessage.recipient_id == b.id)
            .one()
        )
        assert sent_to_a.is_read is True
        assert sent_by_a.is_read is False  # sent by a — untouched

    def test_idempotent_second_call_is_a_noop(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=a.id, content="הי"), b
        )
        key = forum_service.build_conversation_key(a.id, b.id)

        forum_service.mark_conversation_read(db_session, a, key)
        forum_service.mark_conversation_read(db_session, a, key)  # should not raise

        row = (
            db_session.query(DirectMessage)
            .filter(DirectMessage.sender_id == b.id)
            .one()
        )
        assert row.is_read is True

    def test_non_participant_raises_403_and_logs_audit(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        snooper = _make_user(
            db_session, "c@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        key = forum_service.build_conversation_key(a.id, b.id)

        try:
            forum_service.mark_conversation_read(db_session, snooper, key)
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403

        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_ACCESS_DENIED)
            .one()
        )
        assert entry.actor_id == snooper.id

    def test_moderator_cannot_mark_read(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        key = forum_service.build_conversation_key(a.id, b.id)

        try:
            forum_service.mark_conversation_read(db_session, moderator, key)
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403


# ---------------------------------------------------------------------------
# get_inbox()
# ---------------------------------------------------------------------------


def _send_at(db_session, sender, recipient, content, when):
    """
    Send a message, then pin its created_at explicitly.

    SQLite's CURRENT_TIMESTAMP only has one-second resolution, so messages
    sent back-to-back within a test can otherwise tie — making "latest
    message" ordering ambiguous in a way that never happens against Postgres
    (microsecond precision) in production.
    """
    result = forum_service.send_direct_message(
        db_session,
        DirectMessageCreate(recipient_id=recipient.id, content=content),
        sender,
    )
    db_session.query(DirectMessage).filter(DirectMessage.id == result["id"]).update(
        {"created_at": when}
    )
    db_session.commit()
    return result


class TestGetInbox:
    def test_returns_latest_message_per_conversation_most_recent_first(
        self, db_session
    ):
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        alice = _make_user(
            db_session, "alice@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        bob = _make_user(db_session, "bob@example.com", UserType.WIDOW, Sector.HASIDIC)

        _send_at(db_session, me, alice, "הי אליס", datetime(2026, 1, 1, 10, 0, 0))
        _send_at(db_session, bob, me, "הודעה מבוב", datetime(2026, 1, 1, 10, 0, 1))
        _send_at(db_session, me, alice, "עדכון לאליס", datetime(2026, 1, 1, 10, 0, 2))

        result = forum_service.get_inbox(db_session, me)

        assert [c.other_user.id for c in result.items] == [alice.id, bob.id]
        assert result.items[0].last_message_preview == "עדכון לאליס"
        assert result.total == 2

    def test_unread_count_only_counts_messages_sent_to_me(self, db_session):
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        alice = _make_user(
            db_session, "alice@example.com", UserType.WIDOW, Sector.HASIDIC
        )

        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=alice.id, content="הי"), me
        )
        forum_service.send_direct_message(
            db_session,
            DirectMessageCreate(recipient_id=me.id, content="תשובה 1"),
            alice,
        )
        forum_service.send_direct_message(
            db_session,
            DirectMessageCreate(recipient_id=me.id, content="תשובה 2"),
            alice,
        )

        result = forum_service.get_inbox(db_session, me)

        assert result.items[0].unread_count == 2

    def test_excludes_other_users_conversations(self, db_session):
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        alice = _make_user(
            db_session, "alice@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        bob = _make_user(db_session, "bob@example.com", UserType.WIDOW, Sector.HASIDIC)
        forum_service.send_direct_message(
            db_session,
            DirectMessageCreate(recipient_id=bob.id, content="לא בשבילי"),
            alice,
        )

        result = forum_service.get_inbox(db_session, me)

        assert result.items == []
        assert result.total == 0

    def test_query_count_does_not_grow_with_conversation_count(
        self, db_engine, db_session
    ):
        """Directly verifies the ticket's "query count doesn't grow" AC."""
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        for i in range(2):
            partner = _make_user(
                db_session, f"p2-{i}@example.com", UserType.WIDOW, Sector.HASIDIC
            )
            forum_service.send_direct_message(
                db_session,
                DirectMessageCreate(recipient_id=partner.id, content="הי"),
                me,
            )

        def _count_queries() -> int:
            count = 0

            def _listener(*_args, **_kwargs):
                nonlocal count
                count += 1

            event.listen(db_engine, "before_cursor_execute", _listener)
            try:
                forum_service.get_inbox(db_session, me)
            finally:
                event.remove(db_engine, "before_cursor_execute", _listener)
            return count

        queries_with_2_conversations = _count_queries()

        for i in range(20):
            partner = _make_user(
                db_session, f"p20-{i}@example.com", UserType.WIDOW, Sector.HASIDIC
            )
            forum_service.send_direct_message(
                db_session,
                DirectMessageCreate(recipient_id=partner.id, content="הי"),
                me,
            )

        queries_with_22_conversations = _count_queries()

        assert queries_with_2_conversations == queries_with_22_conversations

    def test_moderator_cannot_view_inbox(self, db_session):
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)

        try:
            forum_service.get_inbox(db_session, moderator)
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403

        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_ACCESS_DENIED)
            .one()
        )
        assert entry.actor_id == moderator.id

    def test_admin_cannot_view_inbox(self, db_session):
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)

        try:
            forum_service.get_inbox(db_session, admin)
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403

    def test_professional_cannot_view_inbox(self, db_session):
        professional = _make_user(
            db_session, "prof@example.com", role=UserRole.PROFESSIONAL
        )

        try:
            forum_service.get_inbox(db_session, professional)
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403

    def test_legitimate_read_does_not_create_audit_entry(self, db_session):
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        alice = _make_user(
            db_session, "alice@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=alice.id, content="הי"), me
        )

        forum_service.get_inbox(db_session, me)

        assert db_session.query(AuditLog).count() == 0

    def test_unread_count_drops_to_zero_after_opening_the_conversation(
        self, db_session
    ):
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        alice = _make_user(
            db_session, "alice@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=me.id, content="הי"), alice
        )
        forum_service.send_direct_message(
            db_session,
            DirectMessageCreate(recipient_id=me.id, content="מה נשמע?"),
            alice,
        )
        assert forum_service.get_inbox(db_session, me).items[0].unread_count == 2

        key = forum_service.build_conversation_key(me.id, alice.id)
        forum_service.mark_conversation_read(db_session, me, key)

        assert forum_service.get_inbox(db_session, me).items[0].unread_count == 0

    def test_pagination_slices_and_reports_total(self, db_session):
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        for i in range(3):
            partner = _make_user(
                db_session, f"p-{i}@example.com", UserType.WIDOW, Sector.HASIDIC
            )
            forum_service.send_direct_message(
                db_session,
                DirectMessageCreate(recipient_id=partner.id, content="הי"),
                me,
            )

        page1 = forum_service.get_inbox(db_session, me, page=1, page_size=2)
        page2 = forum_service.get_inbox(db_session, me, page=2, page_size=2)

        assert len(page1.items) == 2
        assert len(page2.items) == 1
        assert page1.total == 3
        assert page2.total == 3


# ---------------------------------------------------------------------------
# get_cell_members()
# ---------------------------------------------------------------------------


class TestGetCellMembers:
    def test_returns_only_same_cell_active_users_excluding_self(self, db_session):
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        same_cell = _make_user(
            db_session, "same@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _make_user(
            db_session, "other-group@example.com", UserType.WIDOWER, Sector.HASIDIC
        )
        _make_user(
            db_session, "other-sector@example.com", UserType.WIDOW, Sector.LITVISH
        )
        _make_user(
            db_session,
            "suspended@example.com",
            UserType.WIDOW,
            Sector.HASIDIC,
            account_status=AccountStatus.SUSPENDED,
        )

        members = forum_service.get_cell_members(db_session, me)

        assert [m.id for m in members] == [same_cell.id]

    def test_moderator_cannot_list_cell_members(self, db_session):
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)

        try:
            forum_service.get_cell_members(db_session, moderator)
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403


# ---------------------------------------------------------------------------
# Endpoint-level tests — direct API calls, per §4.2
# ---------------------------------------------------------------------------


class TestSendMessageEndpoint:
    async def test_success_returns_201(self, client, db_session):
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _login_as(sender)

        r = await client.post(
            MESSAGES_BASE, json={"recipient_id": recipient.id, "content": "שלום"}
        )

        assert r.status_code == 201
        body = r.json()
        assert body["content"] == "שלום"
        assert body["sender"]["id"] == sender.id
        assert body["recipient"]["id"] == recipient.id

    async def test_cross_cell_recipient_id_returns_403(self, client, db_session):
        """§4.2: rejected even when the id is sent manually to the API."""
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        other_cell = _make_user(
            db_session, "b@example.com", UserType.WIDOWER, Sector.SEPHARDIC
        )
        _login_as(sender)

        r = await client.post(
            MESSAGES_BASE, json={"recipient_id": other_cell.id, "content": "שלום"}
        )

        assert r.status_code == 403

    async def test_moderator_returns_403(self, client, db_session):
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _login_as(moderator)

        r = await client.post(
            MESSAGES_BASE, json={"recipient_id": recipient.id, "content": "שלום"}
        )

        assert r.status_code == 403

    async def test_professional_returns_403(self, client, db_session):
        professional = _make_user(
            db_session, "prof@example.com", role=UserRole.PROFESSIONAL
        )
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _login_as(professional)

        r = await client.post(
            MESSAGES_BASE, json={"recipient_id": recipient.id, "content": "שלום"}
        )

        assert r.status_code == 403

    async def test_admin_returns_403(self, client, db_session):
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _login_as(admin)

        r = await client.post(
            MESSAGES_BASE, json={"recipient_id": recipient.id, "content": "שלום"}
        )

        assert r.status_code == 403

    async def test_message_over_max_length_returns_422(self, client, db_session):
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _login_as(sender)

        r = await client.post(
            MESSAGES_BASE,
            json={"recipient_id": recipient.id, "content": "א" * 2001},
        )

        assert r.status_code == 422

    async def test_empty_content_returns_422(self, client, db_session):
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _login_as(sender)

        r = await client.post(
            MESSAGES_BASE, json={"recipient_id": recipient.id, "content": ""}
        )

        assert r.status_code == 422


class TestGetConversationMessagesEndpoint:
    async def test_success_returns_full_history(self, client, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="הי"), a
        )
        key = forum_service.build_conversation_key(a.id, b.id)
        _login_as(a)

        r = await client.get(f"{CONVERSATIONS_BASE}/{key}/messages")

        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["content"] == "הי"

    async def test_opening_a_conversation_marks_it_read(self, client, db_session):
        """End-to-end: the route wires mark_conversation_read() + get_conversation_messages() together."""
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=a.id, content="הי"), b
        )
        key = forum_service.build_conversation_key(a.id, b.id)
        _login_as(a)

        r = await client.get(f"{CONVERSATIONS_BASE}/{key}/messages")

        assert r.status_code == 200
        row = (
            db_session.query(DirectMessage)
            .filter(DirectMessage.sender_id == b.id)
            .one()
        )
        assert row.is_read is True

    async def test_non_participant_returns_403(self, client, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        snooper = _make_user(
            db_session, "c@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        key = forum_service.build_conversation_key(a.id, b.id)
        _login_as(snooper)

        r = await client.get(f"{CONVERSATIONS_BASE}/{key}/messages")

        assert r.status_code == 403

    async def test_moderator_returns_403(self, client, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        key = forum_service.build_conversation_key(a.id, b.id)
        _login_as(moderator)

        r = await client.get(f"{CONVERSATIONS_BASE}/{key}/messages")

        assert r.status_code == 403

    async def test_professional_returns_403(self, client, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        professional = _make_user(
            db_session, "prof@example.com", role=UserRole.PROFESSIONAL
        )
        key = forum_service.build_conversation_key(a.id, b.id)
        _login_as(professional)

        r = await client.get(f"{CONVERSATIONS_BASE}/{key}/messages")

        assert r.status_code == 403

    async def test_admin_returns_403(self, client, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        key = forum_service.build_conversation_key(a.id, b.id)
        _login_as(admin)

        r = await client.get(f"{CONVERSATIONS_BASE}/{key}/messages")

        assert r.status_code == 403


class TestGetCellMembersEndpoint:
    async def test_returns_same_cell_members_only(self, client, db_session):
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        same_cell = _make_user(
            db_session, "same@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _make_user(db_session, "other@example.com", UserType.WIDOWER, Sector.HASIDIC)
        _login_as(me)

        r = await client.get(CELL_MEMBERS_URL)

        assert r.status_code == 200
        body = r.json()
        assert [m["id"] for m in body] == [same_cell.id]
        assert "email" not in body[0]

    async def test_moderator_returns_403(self, client, db_session):
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        _login_as(moderator)

        r = await client.get(CELL_MEMBERS_URL)

        assert r.status_code == 403


class TestGetInboxEndpoint:
    async def test_success_returns_conversations(self, client, db_session):
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        alice = _make_user(
            db_session, "alice@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=alice.id, content="הי"), me
        )
        _login_as(me)

        r = await client.get(MESSAGES_BASE)

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["items"][0]["other_user"]["id"] == alice.id
        assert body["items"][0]["last_message_preview"] == "הי"

    async def test_empty_inbox_returns_200_with_empty_list(self, client, db_session):
        me = _make_user(db_session, "me@example.com", UserType.WIDOW, Sector.HASIDIC)
        _login_as(me)

        r = await client.get(MESSAGES_BASE)

        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_moderator_returns_403(self, client, db_session):
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        _login_as(moderator)

        r = await client.get(MESSAGES_BASE)

        assert r.status_code == 403

    async def test_professional_returns_403(self, client, db_session):
        professional = _make_user(
            db_session, "prof@example.com", role=UserRole.PROFESSIONAL
        )
        _login_as(professional)

        r = await client.get(MESSAGES_BASE)

        assert r.status_code == 403

    async def test_admin_returns_403(self, client, db_session):
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        _login_as(admin)

        r = await client.get(MESSAGES_BASE)

        assert r.status_code == 403
