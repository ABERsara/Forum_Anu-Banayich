"""
Integration tests for the /admin/users/restricted and lift-restriction
endpoints (ABF-162).
"""

import pytest

from app.core.constants import AccountStatus, AuditAction, UserRole
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.user import User

BASE = "/api/v1/admin/users"


@pytest.fixture
def as_user():
    """Override get_current_user and get_current_active_user to return the given user."""

    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
def admin(make_user) -> User:
    return make_user(
        "admin@example.com", role=UserRole.ADMIN, account_status=AccountStatus.ACTIVE
    )


class TestListRestrictedUsers:
    async def test_returns_only_restricted_users(
        self, client, db_session, make_user, as_user, admin
    ) -> None:
        restricted = make_user(
            "restricted@example.com", account_status=AccountStatus.ACTIVE
        )
        restricted.is_report_restricted = True
        make_user("normal@example.com", account_status=AccountStatus.ACTIVE)
        db_session.commit()
        as_user(admin)

        response = await client.get(f"{BASE}/restricted")

        assert response.status_code == 200
        [body] = response.json()
        assert body["email"] == "restricted@example.com"
        assert body["is_report_restricted"] is True

    async def test_empty_when_nobody_is_restricted(
        self, client, make_user, as_user, admin
    ) -> None:
        make_user("normal@example.com", account_status=AccountStatus.ACTIVE)
        as_user(admin)

        response = await client.get(f"{BASE}/restricted")

        assert response.status_code == 200
        assert response.json() == []

    async def test_requires_authentication(self, client) -> None:
        response = await client.get(f"{BASE}/restricted")

        assert response.status_code == 401

    async def test_forbidden_for_non_admin_roles(
        self, client, make_user, as_user
    ) -> None:
        member = make_user("member@example.com", account_status=AccountStatus.ACTIVE)
        as_user(member)

        response = await client.get(f"{BASE}/restricted")

        assert response.status_code == 403

    async def test_forbidden_for_a_moderator(self, client, make_user, as_user) -> None:
        """A moderator is the non-admin role closest to this data — worth its own case."""
        moderator = make_user(
            "moderator@example.com",
            role=UserRole.MODERATOR,
            account_status=AccountStatus.ACTIVE,
        )
        as_user(moderator)

        response = await client.get(f"{BASE}/restricted")

        assert response.status_code == 403


class TestLiftRestriction:
    async def test_clears_the_flag_and_returns_the_user(
        self, client, db_session, make_user, as_user, admin
    ) -> None:
        user = make_user("restricted@example.com", account_status=AccountStatus.ACTIVE)
        user.is_report_restricted = True
        db_session.commit()
        as_user(admin)

        response = await client.patch(f"{BASE}/{user.id}/lift-restriction")

        assert response.status_code == 200
        assert response.json()["is_report_restricted"] is False

    async def test_user_no_longer_appears_on_the_restricted_list(
        self, client, db_session, make_user, as_user, admin
    ) -> None:
        user = make_user("restricted@example.com", account_status=AccountStatus.ACTIVE)
        user.is_report_restricted = True
        db_session.commit()
        as_user(admin)

        await client.patch(f"{BASE}/{user.id}/lift-restriction")
        response = await client.get(f"{BASE}/restricted")

        assert response.json() == []

    async def test_records_the_lift_in_the_audit_log(
        self, client, db_session, make_user, as_user, admin
    ) -> None:
        user = make_user("restricted@example.com", account_status=AccountStatus.ACTIVE)
        user.is_report_restricted = True
        db_session.commit()
        as_user(admin)

        await client.patch(f"{BASE}/{user.id}/lift-restriction")

        log = db_session.query(AuditLog).filter(AuditLog.entity_id == user.id).one()
        assert log.action == AuditAction.USER_RESTRICTED
        assert log.actor_id == admin.id
        assert log.details == {
            "measure": "report_restriction_lifted",
            "automatic": False,
        }

    async def test_unknown_user_returns_404(self, client, as_user, admin) -> None:
        as_user(admin)

        response = await client.patch(f"{BASE}/does-not-exist/lift-restriction")

        assert response.status_code == 404

    async def test_user_who_is_not_restricted_returns_400(
        self, client, make_user, as_user, admin
    ) -> None:
        user = make_user("normal@example.com", account_status=AccountStatus.ACTIVE)
        as_user(admin)

        response = await client.patch(f"{BASE}/{user.id}/lift-restriction")

        assert response.status_code == 400

    async def test_requires_authentication(self, client, make_user) -> None:
        user = make_user("restricted@example.com", account_status=AccountStatus.ACTIVE)

        response = await client.patch(f"{BASE}/{user.id}/lift-restriction")

        assert response.status_code == 401

    async def test_forbidden_for_non_admin_roles(
        self, client, db_session, make_user, as_user
    ) -> None:
        user = make_user("restricted@example.com", account_status=AccountStatus.ACTIVE)
        user.is_report_restricted = True
        member = make_user("member@example.com", account_status=AccountStatus.ACTIVE)
        db_session.commit()
        as_user(member)

        response = await client.patch(f"{BASE}/{user.id}/lift-restriction")

        assert response.status_code == 403

    async def test_forbidden_for_a_moderator(
        self, client, db_session, make_user, as_user
    ) -> None:
        """A moderator is the non-admin role closest to this data — worth its own case."""
        user = make_user("restricted@example.com", account_status=AccountStatus.ACTIVE)
        user.is_report_restricted = True
        moderator = make_user(
            "moderator@example.com",
            role=UserRole.MODERATOR,
            account_status=AccountStatus.ACTIVE,
        )
        db_session.commit()
        as_user(moderator)

        response = await client.patch(f"{BASE}/{user.id}/lift-restriction")

        assert response.status_code == 403
