"""
Tests for private messaging between cell members (ABF-118).

Two layers, matching test_forum_service.py / test_forum_endpoints.py:
  - TestCanMessage / TestSend* / TestGetConversationMessages / TestGetCellMembers
    exercise forum_service functions directly.
  - TestSendMessageEndpoint / TestGetConversationMessagesEndpoint /
    TestGetCellMembersEndpoint go through the real HTTP routes, hitting the
    API directly rather than through any UI — required by §4.2's positive
    AND negative permission checks.
"""

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
