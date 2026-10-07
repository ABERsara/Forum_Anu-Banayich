"""
Integration tests for GET/PUT /users/me: a user reading and editing their own
profile (ABF-165). Today the only editable field is the alert address.

Through the real HTTP route against the test database, required by §4.2's
positive AND negative permission checks: every role may edit their own
address, and nobody may do it without a session or through it change anything
else about the account.
"""

from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.constants import (
    AccountStatus,
    AuditAction,
    GroupVisibility,
    ReportReason,
    ReportTargetType,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.forum import ForumPost
from app.models.user import User
from app.services import report_service

ME = "/api/v1/users/me"

ALL_ROLES = [UserRole.USER, UserRole.MODERATOR, UserRole.ADMIN, UserRole.PROFESSIONAL]

NEW_ADDRESS = "new.alerts@example.com"


def _make_user(
    db_session: Session,
    email: str = "me@example.com",
    role: UserRole = UserRole.USER,
    **kwargs: Any,
) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        account_status=AccountStatus.ACTIVE,
        **kwargs,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def as_user():
    """Override get_current_user and get_current_active_user to return the given user."""

    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


def _profile_audit_entries(db_session: Session) -> list[AuditLog]:
    return (
        db_session.query(AuditLog)
        .filter(AuditLog.action == AuditAction.PROFILE_UPDATED)
        .all()
    )


# ---------------------------------------------------------------------------
# GET /users/me — the form's initial value
# ---------------------------------------------------------------------------


class TestReadMyAlertEmail:
    async def test_the_profile_carries_the_current_alert_email(
        self, client, db_session, as_user
    ) -> None:
        user = _make_user(db_session, alert_email="current.alerts@example.com")
        as_user(user)

        response = await client.get(ME)

        assert response.status_code == 200
        assert response.json()["alert_email"] == "current.alerts@example.com"

    async def test_an_unset_alert_email_reads_as_null(
        self, client, db_session, as_user
    ) -> None:
        as_user(_make_user(db_session))

        response = await client.get(ME)

        assert response.json()["alert_email"] is None


# ---------------------------------------------------------------------------
# PUT /users/me
# ---------------------------------------------------------------------------


class TestUpdateMyAlertEmail:
    @pytest.mark.parametrize("role", ALL_ROLES)
    async def test_every_role_can_set_their_alert_email(
        self, client, db_session, as_user, role
    ) -> None:
        user = _make_user(db_session, role=role)
        as_user(user)

        response = await client.put(ME, json={"alert_email": NEW_ADDRESS})

        assert response.status_code == 200
        assert response.json()["alert_email"] == NEW_ADDRESS
        db_session.refresh(user)
        assert user.alert_email == NEW_ADDRESS

    @pytest.mark.parametrize("role", ALL_ROLES)
    async def test_every_role_can_clear_their_alert_email(
        self, client, db_session, as_user, role
    ) -> None:
        """A cleared address means alerts fall back to the login address."""
        user = _make_user(db_session, role=role, alert_email="old@example.com")
        as_user(user)

        response = await client.put(ME, json={"alert_email": None})

        assert response.status_code == 200
        assert response.json()["alert_email"] is None
        db_session.refresh(user)
        assert user.alert_email is None

    async def test_replaces_an_existing_alert_email(
        self, client, db_session, as_user
    ) -> None:
        user = _make_user(db_session, alert_email="old@example.com")
        as_user(user)

        await client.put(ME, json={"alert_email": NEW_ADDRESS})

        db_session.refresh(user)
        assert user.alert_email == NEW_ADDRESS

    async def test_the_saved_value_is_what_the_profile_reads_back(
        self, client, db_session, as_user
    ) -> None:
        """The round trip the profile screen makes: save, then load."""
        as_user(_make_user(db_session))

        await client.put(ME, json={"alert_email": NEW_ADDRESS})
        response = await client.get(ME)

        assert response.json()["alert_email"] == NEW_ADDRESS

    async def test_the_response_is_the_whole_profile(
        self, client, db_session, as_user
    ) -> None:
        """The client replaces the profile it holds with this body."""
        user = _make_user(db_session, user_type=UserType.WIDOW, sector=Sector.HASIDIC)
        as_user(user)

        response = await client.put(ME, json={"alert_email": NEW_ADDRESS})

        body = response.json()
        assert body["id"] == user.id
        assert body["email"] == "me@example.com"
        assert body["role"] == UserRole.USER
        assert body["user_type"] == UserType.WIDOW
        assert body["sector"] == Sector.HASIDIC

    async def test_an_empty_body_changes_nothing(
        self, client, db_session, as_user
    ) -> None:
        """Partial update: an omitted key is left as it is, not cleared."""
        user = _make_user(db_session, alert_email="kept@example.com")
        as_user(user)

        response = await client.put(ME, json={})

        assert response.status_code == 200
        db_session.refresh(user)
        assert user.alert_email == "kept@example.com"

    async def test_only_the_callers_own_row_changes(
        self, client, db_session, as_user
    ) -> None:
        me = _make_user(db_session)
        other = _make_user(db_session, "other@example.com", alert_email="o@example.com")
        as_user(me)

        await client.put(ME, json={"alert_email": NEW_ADDRESS})

        db_session.refresh(other)
        assert other.alert_email == "o@example.com"

    @pytest.mark.parametrize(
        "invalid",
        [
            "not-an-email",
            "missing-domain@",
            "@example.com",
            "no-dot@localdomain",
            "two@@example.com",
            "spaces in@example.com",
            "",
            123,
        ],
    )
    async def test_rejects_an_invalid_address(
        self, client, db_session, as_user, invalid
    ) -> None:
        user = _make_user(db_session, alert_email="kept@example.com")
        as_user(user)

        response = await client.put(ME, json={"alert_email": invalid})

        assert response.status_code == 422
        db_session.refresh(user)
        assert user.alert_email == "kept@example.com"
        assert _profile_audit_entries(db_session) == []

    @pytest.mark.parametrize(
        "field, value",
        [
            ("email", "new.login@example.com"),
            ("first_name", "שם חדש"),
            ("last_name", "משפחה חדשה"),
            ("role", UserRole.ADMIN),
            ("user_type", UserType.WIDOWER),
            ("sector", Sector.LITVISH),
            ("account_status", AccountStatus.ACTIVE),
        ],
    )
    async def test_rejects_any_other_profile_field(
        self, client, db_session, as_user, field, value
    ) -> None:
        """
        The login address needs the OTP flow, and name, group, sector and role
        are admin decisions. A 422 rather than a silent 200: the client must not
        be told that a change it sent was saved when it was dropped.

        Sent alongside a valid alert address, which is not saved either: the
        request is refused as a whole.
        """
        user = _make_user(db_session, user_type=UserType.WIDOW, sector=Sector.HASIDIC)
        as_user(user)

        response = await client.put(ME, json={"alert_email": NEW_ADDRESS, field: value})

        assert response.status_code == 422
        db_session.refresh(user)
        assert user.alert_email is None
        assert user.email == "me@example.com"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.role == UserRole.USER
        assert user.user_type == UserType.WIDOW
        assert user.sector == Sector.HASIDIC

    async def test_unauthenticated_returns_401(self, client, db_session) -> None:
        """§3.2 negative permission check: no session at all, not just the wrong role."""
        response = await client.put(ME, json={"alert_email": NEW_ADDRESS})

        assert response.status_code == 401

    async def test_unauthenticated_with_an_invalid_body_is_still_401(
        self, client
    ) -> None:
        """The session is checked first: a 422 would confirm the body's shape to anyone."""
        response = await client.put(ME, json={"alert_email": "not-an-email"})

        assert response.status_code == 401

    async def test_an_inactive_account_cannot_edit(self, client, db_session) -> None:
        """
        Same gate as every other /users/me route: get_current_active_user.
        Only get_current_user is overridden, so the real status check runs.
        """
        user = _make_user(db_session)
        user.account_status = AccountStatus.SUSPENDED
        db_session.commit()
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            response = await client.put(ME, json={"alert_email": NEW_ADDRESS})
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 403
        db_session.refresh(user)
        assert user.alert_email is None


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


class TestProfileUpdateAudit:
    async def test_setting_the_address_is_logged_without_the_address(
        self, client, db_session, as_user
    ) -> None:
        user = _make_user(db_session, role=UserRole.MODERATOR)
        as_user(user)

        await client.put(ME, json={"alert_email": NEW_ADDRESS})

        [entry] = _profile_audit_entries(db_session)
        assert entry.actor_id == user.id
        assert entry.entity_type == "User"
        assert entry.entity_id == user.id
        assert entry.details == {
            "updated_fields": ["alert_email"],
            "alert_email_set": True,
        }
        assert NEW_ADDRESS not in str(entry.details)

    async def test_clearing_the_address_is_logged(
        self, client, db_session, as_user
    ) -> None:
        user = _make_user(db_session, alert_email="old@example.com")
        as_user(user)

        await client.put(ME, json={"alert_email": None})

        [entry] = _profile_audit_entries(db_session)
        assert entry.details == {
            "updated_fields": ["alert_email"],
            "alert_email_set": False,
        }

    @pytest.mark.parametrize(
        "stored, body",
        [
            ("same@example.com", {"alert_email": "same@example.com"}),
            (None, {"alert_email": None}),
            ("kept@example.com", {}),
        ],
    )
    async def test_a_save_that_changes_nothing_is_not_logged(
        self, client, db_session, as_user, stored, body
    ) -> None:
        as_user(_make_user(db_session, alert_email=stored))

        response = await client.put(ME, json=body)

        assert response.status_code == 200
        assert _profile_audit_entries(db_session) == []


# ---------------------------------------------------------------------------
# The address saved here is where alerts actually go
# ---------------------------------------------------------------------------


class TestTheSavedAddressReceivesTheAlerts:
    """
    End to end for a moderator: the address saved on the profile is the one
    report alerts are sent to. The member and professional routes are pinned
    in test_professional_service.py.
    """

    @pytest.fixture
    def sent_alerts(self, monkeypatch) -> list[str]:
        recipients: list[str] = []
        monkeypatch.setattr(
            report_service,
            "send_moderator_alert",
            lambda email, report_id, preview: recipients.append(email),
        )
        return recipients

    async def _report_a_post_in_the_moderators_cell(
        self, client, db_session, as_user
    ) -> None:
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        post = ForumPost(
            author_id=author.id,
            group_visibility=GroupVisibility.WIDOWS,
            sector_visibility=SectorVisibility.SEPHARDIC,
            title="כותרת",
            content="תוכן ההודעה",
        )
        db_session.add(post)
        db_session.commit()
        as_user(author)
        response = await client.post(
            f"/api/v1/forum/posts/{post.id}/report",
            json={
                "target_type": ReportTargetType.FORUM_POST,
                "target_id": post.id,
                "reason": ReportReason.OFFENSIVE,
            },
        )
        assert response.status_code == 201

    @pytest.fixture
    def moderator(self, db_session) -> User:
        return _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[{"group": "widow", "sector": "sephardic"}],
        )

    async def test_a_moderator_is_alerted_at_the_address_she_saved(
        self, client, db_session, as_user, sent_alerts, moderator
    ) -> None:
        as_user(moderator)
        await client.put(ME, json={"alert_email": NEW_ADDRESS})

        await self._report_a_post_in_the_moderators_cell(client, db_session, as_user)

        assert sent_alerts == [NEW_ADDRESS]

    async def test_after_clearing_it_she_is_alerted_at_her_login_address(
        self, client, db_session, as_user, sent_alerts, moderator
    ) -> None:
        moderator.alert_email = "old@example.com"
        db_session.commit()
        as_user(moderator)
        await client.put(ME, json={"alert_email": None})

        await self._report_a_post_in_the_moderators_cell(client, db_session, as_user)

        assert sent_alerts == ["mod@example.com"]
