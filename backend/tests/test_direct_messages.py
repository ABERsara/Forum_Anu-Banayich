"""
Tests for private messaging between cell members (ABF-118), the conversations
inbox built on top of it (ABF-119), and the full conversation screen's server
half — cursor paging, read_at receipts and the §5.3 storage cap (ABF-114).

Two layers, matching test_forum_service.py / test_forum_endpoints.py:
  - TestCanMessage / TestSend* / TestGetConversationMessages /
    TestConversationLimit / TestGetCellMembers / TestGetInbox exercise
    forum_service functions directly.
  - TestSendMessageEndpoint / TestGetConversationMessagesEndpoint /
    TestGetCellMembersEndpoint / TestGetInboxEndpoint go through the real HTTP
    routes, hitting the API directly rather than through any UI — required by
    §4.2's positive AND negative permission checks.
"""

from datetime import datetime, timedelta

from sqlalchemy import event

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
from app.core.encryption import decrypt_message
from app.main import app
from app.models.audit import AuditLog
from app.models.forum import DirectMessage
from app.models.report import Report
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


def _send(db_session, sender: User, recipient: User, content: str) -> dict:
    """Send one message and hand back the DirectMessageData inside the result."""
    return forum_service.send_direct_message(
        db_session,
        DirectMessageCreate(recipient_id=recipient.id, content=content),
        sender,
    )["message"]


def _seed_conversation(db_session, sender: User, recipient: User, count: int) -> None:
    """
    Write `count` messages straight to the table, one second apart.

    Bypasses send_direct_message() on purpose: these tests need a specific
    history length and a known order, not the cap enforcement that a real send
    would also run. Content is stored encrypted here too, so anything that
    reads it back goes through the same decrypt path as production.
    """
    from app.core.encryption import encrypt_message

    base = datetime(2026, 8, 1, 12, 0, 0)
    key = forum_service.build_conversation_key(sender.id, recipient.id)
    for index in range(count):
        encrypted, key_version = encrypt_message(f"message-{index:04d}")
        db_session.add(
            DirectMessage(
                sender_id=sender.id,
                recipient_id=recipient.id,
                conversation_key=key,
                content=encrypted,
                key_version=key_version,
                created_at=base + timedelta(seconds=index),
            )
        )
    db_session.commit()


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

        assert result["message"]["content"] == "שלום, מה שלומך?"
        assert result["message"]["read_at"] is None  # unread until b opens it
        assert result["pruned_message_ids"] == []
        assert result["conversation_limit"] == settings.MAX_MESSAGES_PER_CONVERSATION

        row = (
            db_session.query(DirectMessage)
            .filter(DirectMessage.id == result["message"]["id"])
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
        page = forum_service.get_conversation_messages(db_session, a, key)

        assert [r["content"] for r in page["items"]] == ["ראשונה", "שנייה"]
        assert page["has_more"] is False
        assert page["next_cursor"] is None

    def test_does_not_mutate_read_at(self, db_session):
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
        assert row.read_at is None

    def test_well_formed_key_with_no_messages_returns_empty_page(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)

        key = forum_service.build_conversation_key(a.id, b.id)
        page = forum_service.get_conversation_messages(db_session, a, key)

        assert page == {"items": [], "has_more": False, "next_cursor": None}

    def test_first_page_holds_the_newest_messages_oldest_first_inside_it(
        self, db_session
    ):
        """
        A chat screen opens on the *end* of the history, and renders top-down.
        Both halves of that live here: which messages a cursor-less request
        returns (the last `limit`), and in which order they arrive (ascending,
        so the client appends without reversing anything).
        """
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 10)
        key = forum_service.build_conversation_key(a.id, b.id)

        page = forum_service.get_conversation_messages(db_session, a, key, limit=4)

        assert [m["content"] for m in page["items"]] == [
            "message-0006",
            "message-0007",
            "message-0008",
            "message-0009",
        ]
        assert page["has_more"] is True
        assert page["next_cursor"] is not None

    def test_paging_back_covers_every_message_exactly_once(self, db_session):
        """
        The acceptance criterion — scrolling back with neither a gap nor a
        duplicate — checked over the whole history rather than one seam.
        """
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 25)
        key = forum_service.build_conversation_key(a.id, b.id)

        collected: list[str] = []
        cursor = None
        pages = 0
        while True:
            page = forum_service.get_conversation_messages(
                db_session, a, key, limit=7, before=cursor
            )
            collected = [m["content"] for m in page["items"]] + collected
            pages += 1
            if not page["has_more"]:
                break
            cursor = page["next_cursor"]

        assert pages == 4  # 7 + 7 + 7 + 4
        assert collected == [f"message-{i:04d}" for i in range(25)]
        assert len(set(collected)) == 25

    def test_a_message_arriving_mid_scroll_does_not_shift_the_older_pages(
        self, db_session
    ):
        """
        Why the cursor exists at all. With OFFSET, a message appended while the
        reader is paging backwards pushes every older row one place along, and
        the next page re-serves a row already on screen. The cursor names a
        row, so what comes before it does not move.
        """
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 10)
        key = forum_service.build_conversation_key(a.id, b.id)

        first = forum_service.get_conversation_messages(db_session, a, key, limit=4)
        _send(db_session, b, a, "הודעה שהגיעה תוך כדי גלילה")

        second = forum_service.get_conversation_messages(
            db_session, a, key, limit=4, before=first["next_cursor"]
        )

        assert [m["content"] for m in second["items"]] == [
            "message-0002",
            "message-0003",
            "message-0004",
            "message-0005",
        ]
        assert not set(m["id"] for m in second["items"]) & set(
            m["id"] for m in first["items"]
        )

    def test_messages_sharing_a_timestamp_are_not_repeated_across_the_seam(
        self, db_session
    ):
        """
        The tie-break half of the cursor. Every message here carries the same
        created_at, so ordering on that column alone leaves the page boundary
        undefined — and an undefined boundary is what returns a row twice.
        """
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 6)
        key = forum_service.build_conversation_key(a.id, b.id)
        db_session.query(DirectMessage).update(
            {"created_at": datetime(2026, 8, 1, 12, 0, 0)}
        )
        db_session.commit()

        first = forum_service.get_conversation_messages(db_session, a, key, limit=3)
        second = forum_service.get_conversation_messages(
            db_session, a, key, limit=3, before=first["next_cursor"]
        )

        ids = [m["id"] for m in second["items"]] + [m["id"] for m in first["items"]]
        assert len(set(ids)) == 6
        assert second["has_more"] is False

    def test_unreadable_cursor_raises_400(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        key = forum_service.build_conversation_key(a.id, b.id)

        try:
            forum_service.get_conversation_messages(
                db_session, a, key, before="not-a-cursor"
            )
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 400
            assert exc.detail == "errors.invalid_cursor"

    def test_a_cursor_is_checked_after_permission_not_before(self, db_session):
        """
        A malformed cursor must not become a way to tell a conversation that
        exists from one that does not: an outsider gets the same 403 either
        way, and never the 400.
        """
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        snooper = _make_user(
            db_session, "c@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        key = forum_service.build_conversation_key(a.id, b.id)

        try:
            forum_service.get_conversation_messages(
                db_session, snooper, key, before="not-a-cursor"
            )
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403

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
        assert sent_to_a.read_at is not None
        assert sent_by_a.read_at is None  # sent by a — untouched

    def test_idempotent_second_call_is_a_noop(self, db_session):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=a.id, content="הי"), b
        )
        key = forum_service.build_conversation_key(a.id, b.id)

        forum_service.mark_conversation_read(db_session, a, key)
        row = (
            db_session.query(DirectMessage)
            .filter(DirectMessage.sender_id == b.id)
            .one()
        )
        first_read_at = row.read_at
        assert first_read_at is not None

        forum_service.mark_conversation_read(db_session, a, key)  # should not raise

        db_session.refresh(row)
        # Not merely "still read" — the *same* instant. Re-opening a thread
        # must not restamp a message that was read yesterday, which is what a
        # receipt showing a time depends on.
        assert row.read_at == first_read_at

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
    Send a message, then pin its created_at to a chosen instant.

    Not a workaround for tied timestamps any more — ABF-114 gave
    DirectMessage.created_at a Python-side microsecond default, so
    back-to-back sends no longer collide even on SQLite. It is here so a test
    can put a message at a *specific* time, days apart, without sleeping.
    """
    result = _send(db_session, sender, recipient, content)
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
# _enforce_conversation_limit() — spec §5.3's 1,000-message cap
# ---------------------------------------------------------------------------


def _report_message(db_session, reporter: User, message: DirectMessage, decision):
    """File a report on one private message, at the given decision state."""
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


def _oldest_message(db_session, conversation_key: str) -> DirectMessage:
    return (
        db_session.query(DirectMessage)
        .filter(DirectMessage.conversation_key == conversation_key)
        .order_by(DirectMessage.created_at.asc(), DirectMessage.id.asc())
        .first()
    )


class TestConversationLimit:
    """
    The cap is read from settings, so these tests lower it instead of writing
    a thousand rows — the behaviour under test is "one over the limit", not
    the number itself.
    """

    def test_send_below_the_cap_deletes_nothing(self, db_session, monkeypatch):
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 5)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 3)

        result = _send(db_session, a, b, "עוד אחת")

        assert result is not None
        assert db_session.query(DirectMessage).count() == 4

    def test_the_send_that_reaches_the_cap_exactly_deletes_nothing(
        self, db_session, monkeypatch
    ):
        """The boundary: 1,000 is allowed, only the 1,001st costs a message."""
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 5)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 4)

        result = forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="החמישית"), a
        )

        assert result["pruned_message_ids"] == []
        assert db_session.query(DirectMessage).count() == 5

    def test_the_next_send_deletes_the_oldest_message_only(
        self, db_session, monkeypatch
    ):
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 5)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 5)
        key = forum_service.build_conversation_key(a.id, b.id)
        oldest_id = _oldest_message(db_session, key).id

        result = forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="השישית"), a
        )

        assert result["pruned_message_ids"] == [oldest_id]
        assert db_session.query(DirectMessage).count() == 5
        assert (
            db_session.query(DirectMessage)
            .filter(DirectMessage.id == oldest_id)
            .first()
            is None
        )
        remaining = [
            m["content"]
            for m in forum_service.get_conversation_messages(db_session, a, key)[
                "items"
            ]
        ]
        assert remaining == [
            "message-0001",
            "message-0002",
            "message-0003",
            "message-0004",
            "השישית",
        ]

    def test_the_ids_name_the_messages_that_actually_went(
        self, db_session, monkeypatch
    ):
        """
        Why the response carries ids and not a count. With the oldest message
        protected, the message deleted is the *second* oldest — so a client
        trimming "the first N off the top" would take the wrong bubble off the
        screen and leave the deleted one showing.
        """
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 5)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 5)
        key = forum_service.build_conversation_key(a.id, b.id)
        oldest = _oldest_message(db_session, key)
        oldest_id = oldest.id
        _report_message(db_session, b, oldest, ReportDecision.PENDING)
        second_oldest_id = (
            db_session.query(DirectMessage)
            .filter(
                DirectMessage.conversation_key == key,
                DirectMessage.id != oldest_id,
            )
            .order_by(DirectMessage.created_at.asc(), DirectMessage.id.asc())
            .first()
            .id
        )

        result = forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="השישית"), a
        )

        assert result["pruned_message_ids"] == [second_oldest_id]

    def test_an_openly_reported_message_is_skipped_and_the_next_one_goes(
        self, db_session, monkeypatch
    ):
        """
        The §5.3 exemption. A moderator may only ever see a private message
        that was reported to them, so pruning one with an open report would
        destroy the evidence before the report is ruled on.
        """
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 5)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 5)
        key = forum_service.build_conversation_key(a.id, b.id)
        oldest = _oldest_message(db_session, key)
        oldest_id = oldest.id
        _report_message(db_session, b, oldest, ReportDecision.PENDING)

        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="השישית"), a
        )

        assert (
            db_session.query(DirectMessage)
            .filter(DirectMessage.id == oldest_id)
            .first()
            is not None
        )
        remaining = [
            m["content"]
            for m in forum_service.get_conversation_messages(db_session, a, key)[
                "items"
            ]
        ]
        assert remaining == [
            "message-0000",
            "message-0002",
            "message-0003",
            "message-0004",
            "השישית",
        ]

    def test_a_decided_report_stops_protecting_its_message(
        self, db_session, monkeypatch
    ):
        """
        "Open" is the whole of the exemption: once a moderator has ruled, the
        message is ordinary history again and prunes in its turn. Without this
        a single old report would pin a message in place forever.
        """
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 5)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 5)
        key = forum_service.build_conversation_key(a.id, b.id)
        oldest = _oldest_message(db_session, key)
        oldest_id = oldest.id
        _report_message(db_session, b, oldest, ReportDecision.INVALID)

        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="השישית"), a
        )

        assert (
            db_session.query(DirectMessage)
            .filter(DirectMessage.id == oldest_id)
            .first()
            is None
        )

    def test_a_conversation_of_nothing_but_reported_messages_keeps_all_of_them(
        self, db_session, monkeypatch
    ):
        """
        The cap is a target, not an invariant. When every candidate is
        protected the conversation grows past the limit rather than deleting
        evidence, and pruned_count says nothing was dropped — so the screen
        does not announce a deletion that never happened.
        """
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 3)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 3)
        key = forum_service.build_conversation_key(a.id, b.id)
        for message in db_session.query(DirectMessage).all():
            _report_message(db_session, b, message, ReportDecision.PENDING)

        result = forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="הרביעית"), a
        )

        assert result["pruned_message_ids"] == []
        assert (
            db_session.query(DirectMessage)
            .filter(DirectMessage.conversation_key == key)
            .count()
            == 4
        )

    def test_a_report_on_a_forum_post_does_not_protect_a_message(
        self, db_session, monkeypatch
    ):
        """
        The exemption matches on target_type as well as id. Report ids are
        opaque strings, so a report filed against some other kind of content
        must not accidentally shield a message that happens to share its id.
        """
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 5)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 5)
        key = forum_service.build_conversation_key(a.id, b.id)
        oldest_id = _oldest_message(db_session, key).id
        db_session.add(
            Report(
                reporter_id=b.id,
                target_type=ReportTargetType.FORUM_POST,
                target_id=oldest_id,
                reported_user_id=a.id,
                reason=ReportReason.SPAM,
                decision=ReportDecision.PENDING,
            )
        )
        db_session.commit()

        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="השישית"), a
        )

        assert (
            db_session.query(DirectMessage)
            .filter(DirectMessage.id == oldest_id)
            .first()
            is None
        )

    def test_a_pruned_message_leaves_an_audit_entry_without_its_content(
        self, db_session, monkeypatch
    ):
        """
        §9.3 — deleting a user's own content is a sensitive action, and the
        audit log is the only place it stays visible. It records which message
        went, never a word of what it said.
        """
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 3)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 3)
        key = forum_service.build_conversation_key(a.id, b.id)
        oldest_id = _oldest_message(db_session, key).id

        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="סודי ביותר"), a
        )

        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.DIRECT_MESSAGE_PRUNED)
            .one()
        )
        assert entry.actor_id == a.id
        assert entry.entity_type == "DirectMessage"
        assert entry.entity_id == oldest_id
        assert entry.details == {
            "conversation_key": key,
            "reason": "storage_cap",
        }
        assert "message-0000" not in str(entry.details)

    def test_the_cap_counts_one_conversation_not_the_whole_table(
        self, db_session, monkeypatch
    ):
        """
        §5.3 caps messages *per conversation*. Grouping by conversation_key is
        what keeps a busy pair from evicting a quiet pair's history.
        """
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 3)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        c = _make_user(db_session, "c@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 3)
        _seed_conversation(db_session, a, c, 2)
        other_key = forum_service.build_conversation_key(a.id, c.id)

        forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="הרביעית"), a
        )

        assert (
            db_session.query(DirectMessage)
            .filter(DirectMessage.conversation_key == other_key)
            .count()
            == 2
        )

    def test_the_message_just_sent_is_never_the_one_deleted(
        self, db_session, monkeypatch
    ):
        """A cap of one: the new message must survive its own send."""
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 1)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 1)
        key = forum_service.build_conversation_key(a.id, b.id)

        result = forum_service.send_direct_message(
            db_session, DirectMessageCreate(recipient_id=b.id, content="האחרונה"), a
        )

        assert len(result["pruned_message_ids"]) == 1
        page = forum_service.get_conversation_messages(db_session, a, key)
        assert [m["content"] for m in page["items"]] == ["האחרונה"]

    def test_a_blocked_send_prunes_nothing(self, db_session, monkeypatch):
        """
        Enforcement runs after the message is stored, never before: a send
        that is rejected must not have cost the conversation any history.
        """
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 2)
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        outsider = _make_user(
            db_session, "x@example.com", UserType.WIDOWER, Sector.SEPHARDIC
        )
        _seed_conversation(db_session, a, b, 3)

        try:
            forum_service.send_direct_message(
                db_session,
                DirectMessageCreate(recipient_id=outsider.id, content="שלום"),
                a,
            )
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert exc.status_code == 403

        assert db_session.query(DirectMessage).count() == 3


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
        assert body["message"]["content"] == "שלום"
        assert body["message"]["sender"]["id"] == sender.id
        assert body["message"]["recipient"]["id"] == recipient.id
        assert body["message"]["read_at"] is None
        assert body["pruned_message_ids"] == []
        assert body["conversation_limit"] == settings.MAX_MESSAGES_PER_CONVERSATION

    async def test_crossing_the_cap_reports_what_it_deleted(
        self, client, db_session, monkeypatch
    ):
        """
        The acceptance criterion end to end: on the message past the cap, the
        response says which older message went, and names the limit — the two
        things the screen needs to tell the user rather than losing history in
        silence.
        """
        monkeypatch.setattr(settings, "MAX_MESSAGES_PER_CONVERSATION", 3)
        sender = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        recipient = _make_user(
            db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _seed_conversation(db_session, sender, recipient, 3)
        key = forum_service.build_conversation_key(sender.id, recipient.id)
        oldest_id = _oldest_message(db_session, key).id
        _login_as(sender)

        r = await client.post(
            MESSAGES_BASE, json={"recipient_id": recipient.id, "content": "הרביעית"}
        )

        assert r.status_code == 201
        body = r.json()
        assert body["pruned_message_ids"] == [oldest_id]
        assert body["conversation_limit"] == 3

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
        assert len(body["items"]) == 1
        assert body["items"][0]["content"] == "הי"
        assert body["has_more"] is False
        assert body["next_cursor"] is None

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
        assert row.read_at is not None

    async def test_scrolling_back_does_not_mark_anything_read(self, client, db_session):
        """
        Only opening a conversation says "seen". A request carrying a cursor is
        the reader scrolling back through what she has already been shown, and
        the route must not turn that into a write on every page.
        """
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, b, a, 6)
        key = forum_service.build_conversation_key(a.id, b.id)
        _login_as(a)

        first = await client.get(
            f"{CONVERSATIONS_BASE}/{key}/messages", params={"limit": 3}
        )
        db_session.query(DirectMessage).update({"read_at": None})
        db_session.commit()

        r = await client.get(
            f"{CONVERSATIONS_BASE}/{key}/messages",
            params={"limit": 3, "before": first.json()["next_cursor"]},
        )

        assert r.status_code == 200
        unread = (
            db_session.query(DirectMessage)
            .filter(DirectMessage.read_at.is_(None))
            .count()
        )
        assert unread == 6

    async def test_paging_walks_the_history_without_repeating_a_message(
        self, client, db_session
    ):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        _seed_conversation(db_session, a, b, 7)
        key = forum_service.build_conversation_key(a.id, b.id)
        _login_as(a)

        first = (
            await client.get(
                f"{CONVERSATIONS_BASE}/{key}/messages", params={"limit": 3}
            )
        ).json()
        second = (
            await client.get(
                f"{CONVERSATIONS_BASE}/{key}/messages",
                params={"limit": 3, "before": first["next_cursor"]},
            )
        ).json()
        third = (
            await client.get(
                f"{CONVERSATIONS_BASE}/{key}/messages",
                params={"limit": 3, "before": second["next_cursor"]},
            )
        ).json()

        contents = [
            m["content"] for page in (third, second, first) for m in page["items"]
        ]
        assert contents == [f"message-{i:04d}" for i in range(7)]
        assert third["has_more"] is False
        assert third["next_cursor"] is None

    async def test_unreadable_cursor_returns_400_with_a_translation_key(
        self, client, db_session
    ):
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        key = forum_service.build_conversation_key(a.id, b.id)
        _login_as(a)

        r = await client.get(
            f"{CONVERSATIONS_BASE}/{key}/messages", params={"before": "%%%"}
        )

        assert r.status_code == 400
        assert r.json()["detail"] == "errors.invalid_cursor"

    async def test_limit_above_the_maximum_is_rejected(self, client, db_session):
        """The page size bounds how much content one request can decrypt."""
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        key = forum_service.build_conversation_key(a.id, b.id)
        _login_as(a)

        r = await client.get(
            f"{CONVERSATIONS_BASE}/{key}/messages",
            params={"limit": forum_service.CONVERSATION_MAX_PAGE_SIZE + 1},
        )

        assert r.status_code == 422

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

    async def test_non_participant_with_a_valid_cursor_still_returns_403(
        self, client, db_session
    ):
        """
        §4.2, straight at the API: a cursor is not a way in. The outsider here
        holds a cursor this conversation really issued, and still gets the same
        403 as with no cursor at all — permission is checked before the cursor
        is even read, so the reply cannot say whether the cursor was good.
        """
        a = _make_user(db_session, "a@example.com", UserType.WIDOW, Sector.HASIDIC)
        b = _make_user(db_session, "b@example.com", UserType.WIDOW, Sector.HASIDIC)
        outsider = _make_user(
            db_session, "c@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _seed_conversation(db_session, a, b, 4)
        key = forum_service.build_conversation_key(a.id, b.id)
        _login_as(a)
        cursor = (
            await client.get(
                f"{CONVERSATIONS_BASE}/{key}/messages", params={"limit": 2}
            )
        ).json()["next_cursor"]

        _login_as(outsider)
        r = await client.get(
            f"{CONVERSATIONS_BASE}/{key}/messages",
            params={"limit": 2, "before": cursor},
        )

        assert r.status_code == 403
        assert r.json()["detail"] == "errors.dm_forbidden"

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
