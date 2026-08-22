"""
Integration tests for the /admin/moderators endpoints (moderator roster).
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

BASE = "/api/v1/admin/moderators"

#: The two cells of the acceptance scenario: Sephardic widows and widowers.
WIDOWS_SEPHARDIC = {"group": UserType.WIDOW, "sector": Sector.SEPHARDIC}
WIDOWERS_SEPHARDIC = {"group": UserType.WIDOWER, "sector": Sector.SEPHARDIC}

#: Those same two cells in the canonical order the API stores them in: the
#: order UserType and Sector declare their members, widower before widow.
SEPHARDIC_SPOUSES = [WIDOWERS_SEPHARDIC, WIDOWS_SEPHARDIC]
SEPHARDIC_SPOUSES_JSON = [
    {"group": "widower", "sector": "sephardic"},
    {"group": "widow", "sector": "sephardic"},
]


def _make_user(
    db_session: Session,
    role: UserRole,
    email: str,
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


def _make_moderator(db_session: Session, email: str, **kwargs: Any) -> User:
    defaults: dict[str, Any] = {
        "moderator_cells": [{"group": "widow", "sector": "sephardic"}],
        "alert_email": "alerts@example.com",
    }
    defaults.update(kwargs)
    return _make_user(db_session, UserRole.MODERATOR, email, **defaults)


def _create_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "first_name": "שרה",
        "last_name": "לוי",
        "email": "sara.levi@example.com",
        "moderator_cells": [WIDOWS_SEPHARDIC, WIDOWERS_SEPHARDIC],
        "alert_email": "alerts.sara@example.com",
    }
    body.update(overrides)
    return body


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
def admin(db_session: Session) -> User:
    return _make_user(db_session, UserRole.ADMIN, "admin@example.com")


class TestListModerators:
    async def test_returns_every_moderator_with_their_cells(
        self, client, db_session, as_user, admin
    ) -> None:
        as_user(admin)
        _make_moderator(
            db_session,
            "mod@example.com",
            moderator_cells=[
                {"group": "widow", "sector": "sephardic"},
                {"group": "widower", "sector": "sephardic"},
            ],
        )

        response = await client.get(BASE)

        assert response.status_code == 200
        [moderator] = response.json()
        assert moderator["email"] == "mod@example.com"
        assert moderator["role"] == UserRole.MODERATOR
        assert moderator["moderator_cells"] == [
            {"group": UserType.WIDOW, "sector": Sector.SEPHARDIC},
            {"group": UserType.WIDOWER, "sector": Sector.SEPHARDIC},
        ]
        assert moderator["alert_email"] == "alerts@example.com"

    async def test_excludes_users_who_are_not_moderators(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_user(
            db_session,
            UserRole.USER,
            "member@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.GENERAL,
        )
        as_user(admin)

        response = await client.get(BASE)

        assert response.status_code == 200
        assert response.json() == []

    async def test_reads_a_null_cells_column_as_an_empty_list(
        self, client, db_session, as_user, admin
    ) -> None:
        """The contract is always a list, so the client never branches on null."""
        _make_moderator(db_session, "legacy@example.com", moderator_cells=None)
        as_user(admin)

        response = await client.get(BASE)

        [moderator] = response.json()
        assert moderator["moderator_cells"] == []

    async def test_requires_authentication(self, client) -> None:
        response = await client.get(BASE)

        assert response.status_code == 401

    async def test_forbidden_for_non_admin_roles(
        self, client, db_session, as_user
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(moderator)

        response = await client.get(BASE)

        assert response.status_code == 403


class TestAddModerator:
    async def test_creates_and_returns_the_new_moderator(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        response = await client.post(BASE, json=_create_body())

        assert response.status_code == 201
        body = response.json()
        assert body["id"]
        assert body["first_name"] == "שרה"
        assert body["role"] == UserRole.MODERATOR
        assert body["account_status"] == AccountStatus.ACTIVE
        assert body["moderator_cells"] == SEPHARDIC_SPOUSES
        assert body["alert_email"] == "alerts.sara@example.com"

    async def test_the_new_moderator_appears_on_the_roster(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)
        created = (await client.post(BASE, json=_create_body())).json()

        response = await client.get(BASE)

        assert [m["id"] for m in response.json()] == [created["id"]]

    async def test_stores_the_cells_in_the_agreed_json_shape(
        self, client, db_session, as_user, admin
    ) -> None:
        """S2: the column holds plain {"group", "sector"} dicts of enum values."""
        as_user(admin)

        created = (await client.post(BASE, json=_create_body())).json()

        moderator = db_session.query(User).filter(User.id == created["id"]).one()
        assert moderator.moderator_cells == SEPHARDIC_SPOUSES_JSON

    async def test_the_account_cannot_be_signed_into_yet(
        self, client, db_session, as_user, admin
    ) -> None:
        """No credentials until the invitation flow — but not a blank password."""
        as_user(admin)

        created = (await client.post(BASE, json=_create_body())).json()

        moderator = db_session.query(User).filter(User.id == created["id"]).one()
        assert moderator.password_hash

    async def test_an_alert_email_is_optional(self, client, as_user, admin) -> None:
        as_user(admin)

        response = await client.post(BASE, json=_create_body(alert_email=None))

        assert response.status_code == 201
        assert response.json()["alert_email"] is None

    async def test_orders_and_dedupes_the_submitted_cells(
        self, client, as_user, admin
    ) -> None:
        """Ticking order is not meaningful, so it must not reach the database."""
        as_user(admin)

        response = await client.post(
            BASE,
            json=_create_body(
                moderator_cells=[
                    WIDOWS_SEPHARDIC,
                    WIDOWERS_SEPHARDIC,
                    WIDOWS_SEPHARDIC,
                ]
            ),
        )

        assert response.json()["moderator_cells"] == SEPHARDIC_SPOUSES

    async def test_records_the_appointment_in_the_audit_log(
        self, client, db_session, as_user, admin
    ) -> None:
        as_user(admin)

        created = (await client.post(BASE, json=_create_body())).json()

        log = (
            db_session.query(AuditLog).filter(AuditLog.entity_id == created["id"]).one()
        )
        assert log.action == AuditAction.MODERATOR_ASSIGNED
        assert log.actor_id == admin.id
        assert log.details == {
            "cells": SEPHARDIC_SPOUSES_JSON,
            "alert_email_set": True,
            "reinstated": False,
        }

    async def test_the_audit_entry_never_carries_the_alert_address(
        self, client, db_session, as_user, admin
    ) -> None:
        as_user(admin)

        created = (await client.post(BASE, json=_create_body())).json()

        log = (
            db_session.query(AuditLog).filter(AuditLog.entity_id == created["id"]).one()
        )
        assert "alerts.sara@example.com" not in str(log.details)

    async def test_rejects_an_email_already_registered(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_user(
            db_session,
            UserRole.USER,
            "taken@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.GENERAL,
        )
        as_user(admin)

        response = await client.post(BASE, json=_create_body(email="taken@example.com"))

        assert response.status_code == 409

    @pytest.mark.parametrize(
        "invalid",
        [
            pytest.param({"moderator_cells": []}, id="no_cells"),
            pytest.param({"moderator_cells": None}, id="null_cells"),
            pytest.param(
                {"moderator_cells": [{"group": "widow"}]}, id="cell_without_sector"
            ),
            pytest.param(
                {"moderator_cells": [{"group": "nobody", "sector": "sephardic"}]},
                id="unknown_group",
            ),
            pytest.param(
                {"moderator_cells": [{"group": "widow", "sector": "mars"}]},
                id="unknown_sector",
            ),
            pytest.param(
                {"moderator_cells": [{"group": "all", "sector": "all"}]},
                id="wildcard_is_not_a_cell",
            ),
            pytest.param({"email": "not-an-email"}, id="malformed_email"),
            pytest.param({"alert_email": "not-an-email"}, id="malformed_alert_email"),
            pytest.param({"first_name": "א"}, id="too_short_name"),
        ],
    )
    async def test_rejects_invalid_bodies(
        self, client, as_user, admin, invalid: dict[str, Any]
    ) -> None:
        as_user(admin)

        response = await client.post(BASE, json=_create_body(**invalid))

        assert response.status_code == 422

    async def test_forbidden_for_non_admin_roles(
        self, client, db_session, as_user
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(moderator)

        response = await client.post(BASE, json=_create_body())

        assert response.status_code == 403


class TestUpdateModerator:
    async def test_updates_the_assigned_cells(
        self, client, db_session, as_user, admin
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)

        response = await client.patch(
            f"{BASE}/{moderator.id}",
            json={"moderator_cells": [WIDOWERS_SEPHARDIC]},
        )

        assert response.status_code == 200
        assert response.json()["moderator_cells"] == [WIDOWERS_SEPHARDIC]

    async def test_updates_the_alert_email_on_its_own(
        self, client, db_session, as_user, admin
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)

        response = await client.patch(
            f"{BASE}/{moderator.id}", json={"alert_email": "new.alerts@example.com"}
        )

        body = response.json()
        assert body["alert_email"] == "new.alerts@example.com"
        assert body["moderator_cells"] == [WIDOWS_SEPHARDIC]

    async def test_clearing_the_alert_email_is_allowed(
        self, client, db_session, as_user, admin
    ) -> None:
        """Cleared alerts fall back to the moderator's own address."""
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)

        response = await client.patch(
            f"{BASE}/{moderator.id}", json={"alert_email": None}
        )

        assert response.status_code == 200
        assert response.json()["alert_email"] is None

    async def test_rejects_an_explicit_null_that_would_empty_the_cells(
        self, client, db_session, as_user, admin
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)

        response = await client.patch(
            f"{BASE}/{moderator.id}", json={"moderator_cells": None}
        )

        assert response.status_code == 422

    async def test_rejects_an_empty_cell_list(
        self, client, db_session, as_user, admin
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)

        response = await client.patch(
            f"{BASE}/{moderator.id}", json={"moderator_cells": []}
        )

        assert response.status_code == 422

    async def test_records_the_update_in_the_audit_log(
        self, client, db_session, as_user, admin
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)

        await client.patch(
            f"{BASE}/{moderator.id}", json={"moderator_cells": [WIDOWERS_SEPHARDIC]}
        )

        log = (
            db_session.query(AuditLog).filter(AuditLog.entity_id == moderator.id).one()
        )
        assert log.action == AuditAction.MODERATOR_UPDATED
        assert log.actor_id == admin.id
        assert log.details == {
            "updated_fields": ["moderator_cells"],
            "cells": [{"group": "widower", "sector": "sephardic"}],
            "alert_email_set": True,
        }

    async def test_re_submitting_the_same_cells_is_not_logged_as_an_edit(
        self, client, db_session, as_user, admin
    ) -> None:
        """Same cells, different ticking order — nothing actually changed."""
        moderator = _make_moderator(
            db_session, "mod@example.com", moderator_cells=SEPHARDIC_SPOUSES_JSON
        )
        as_user(admin)

        response = await client.patch(
            f"{BASE}/{moderator.id}",
            json={"moderator_cells": [WIDOWS_SEPHARDIC, WIDOWERS_SEPHARDIC]},
        )

        assert response.status_code == 200
        assert db_session.query(AuditLog).count() == 0

    async def test_unknown_moderator_returns_404(self, client, as_user, admin) -> None:
        as_user(admin)

        response = await client.patch(
            f"{BASE}/does-not-exist", json={"moderator_cells": [WIDOWS_SEPHARDIC]}
        )

        assert response.status_code == 404

    async def test_cannot_edit_a_user_who_is_not_a_moderator(
        self, client, db_session, as_user, admin
    ) -> None:
        member = _make_user(
            db_session,
            UserRole.USER,
            "member@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.GENERAL,
        )
        as_user(admin)

        response = await client.patch(
            f"{BASE}/{member.id}", json={"moderator_cells": [WIDOWS_SEPHARDIC]}
        )

        assert response.status_code == 400

    async def test_forbidden_for_non_admin_roles(
        self, client, db_session, as_user
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(moderator)

        response = await client.patch(
            f"{BASE}/{moderator.id}", json={"moderator_cells": [WIDOWS_SEPHARDIC]}
        )

        assert response.status_code == 403


class TestRemoveModerator:
    async def test_removes_the_moderator_from_the_roster(
        self, client, db_session, as_user, admin
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)

        response = await client.delete(f"{BASE}/{moderator.id}")

        assert response.status_code == 204
        assert (await client.get(BASE)).json() == []

    async def test_keeps_the_row_but_revokes_the_appointment(
        self, client, db_session, as_user, admin
    ) -> None:
        """
        Audit entries and decided reports reference the row, so it stays —
        cancelled, with nothing left routing to it.
        """
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)

        await client.delete(f"{BASE}/{moderator.id}")

        db_session.refresh(moderator)
        assert moderator.account_status == AccountStatus.CANCELLED
        assert moderator.moderator_cells == []
        assert moderator.alert_email is None

    async def test_records_the_removal_in_the_audit_log(
        self, client, db_session, as_user, admin
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)

        await client.delete(f"{BASE}/{moderator.id}")

        log = (
            db_session.query(AuditLog).filter(AuditLog.entity_id == moderator.id).one()
        )
        assert log.action == AuditAction.MODERATOR_REMOVED
        assert log.actor_id == admin.id
        assert log.details == {
            "revoked_cells": [{"group": "widow", "sector": "sephardic"}]
        }

    async def test_removing_twice_reports_that_they_are_already_gone(
        self, client, db_session, as_user, admin
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)
        await client.delete(f"{BASE}/{moderator.id}")

        response = await client.delete(f"{BASE}/{moderator.id}")

        assert response.status_code == 400

    async def test_a_removed_moderator_can_no_longer_be_edited(
        self, client, db_session, as_user, admin
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)
        await client.delete(f"{BASE}/{moderator.id}")

        response = await client.patch(
            f"{BASE}/{moderator.id}", json={"moderator_cells": [WIDOWS_SEPHARDIC]}
        )

        assert response.status_code == 400

    async def test_the_same_person_can_be_appointed_again(
        self, client, db_session, as_user, admin
    ) -> None:
        """Removal must not lock the address out of the roster forever."""
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(admin)
        await client.delete(f"{BASE}/{moderator.id}")

        response = await client.post(
            BASE, json=_create_body(email="mod@example.com", first_name="שרה")
        )

        assert response.status_code == 201
        assert response.json()["id"] == moderator.id
        assert response.json()["account_status"] == AccountStatus.ACTIVE
        assert [m["email"] for m in (await client.get(BASE)).json()] == [
            "mod@example.com"
        ]

    async def test_unknown_moderator_returns_404(self, client, as_user, admin) -> None:
        as_user(admin)

        response = await client.delete(f"{BASE}/does-not-exist")

        assert response.status_code == 404

    async def test_cannot_remove_a_user_who_is_not_a_moderator(
        self, client, db_session, as_user, admin
    ) -> None:
        member = _make_user(
            db_session,
            UserRole.USER,
            "member@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.GENERAL,
        )
        as_user(admin)

        response = await client.delete(f"{BASE}/{member.id}")

        assert response.status_code == 400
        db_session.refresh(member)
        assert member.account_status == AccountStatus.ACTIVE

    async def test_forbidden_for_non_admin_roles(
        self, client, db_session, as_user
    ) -> None:
        moderator = _make_moderator(db_session, "mod@example.com")
        as_user(moderator)

        response = await client.delete(f"{BASE}/{moderator.id}")

        assert response.status_code == 403


class TestAppointedModeratorReceivesReportAlerts:
    """
    The acceptance scenario: an admin appoints a moderator over the Sephardic
    widow/widower cells, a member reports a post, and the alert reaches the
    address the admin registered.

    Routing by cell is not wired up yet (report_service._moderator_emails_for
    still alerts every active moderator — Sprint 4); what these tests pin down
    is that appointing and removing a moderator is what decides whether the
    alerts arrive at all.
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

    def _post_in_the_sephardic_widows_cell(
        self, db_session: Session, author: User
    ) -> ForumPost:
        post = ForumPost(
            author_id=author.id,
            group_visibility=GroupVisibility.WIDOWS,
            sector_visibility=SectorVisibility.SEPHARDIC,
            title="כותרת",
            content="תוכן ההודעה",
        )
        db_session.add(post)
        db_session.commit()
        return post

    async def _report_the_post(self, client, post: ForumPost):
        return await client.post(
            f"/api/v1/forum/posts/{post.id}/report",
            json={
                "target_type": ReportTargetType.FORUM_POST,
                "target_id": post.id,
                "reason": ReportReason.OFFENSIVE,
            },
        )

    async def test_the_appointed_moderator_is_alerted_at_their_alert_email(
        self, client, db_session, as_user, admin, sent_alerts
    ) -> None:
        as_user(admin)
        await client.post(BASE, json=_create_body())
        author = _make_user(
            db_session,
            UserRole.USER,
            "author@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        reporter = _make_user(
            db_session,
            UserRole.USER,
            "reporter@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        post = self._post_in_the_sephardic_widows_cell(db_session, author)
        as_user(reporter)

        response = await self._report_the_post(client, post)

        assert response.status_code == 201
        assert sent_alerts == ["alerts.sara@example.com"]

    async def test_a_moderator_without_an_alert_email_is_reached_at_their_own(
        self, client, db_session, as_user, admin, sent_alerts
    ) -> None:
        as_user(admin)
        await client.post(BASE, json=_create_body(alert_email=None))
        author = _make_user(
            db_session,
            UserRole.USER,
            "author@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        post = self._post_in_the_sephardic_widows_cell(db_session, author)
        as_user(author)

        await self._report_the_post(client, post)

        assert sent_alerts == ["sara.levi@example.com"]

    async def test_a_removed_moderator_stops_being_alerted(
        self, client, db_session, as_user, admin, sent_alerts
    ) -> None:
        as_user(admin)
        appointed = (await client.post(BASE, json=_create_body())).json()
        await client.delete(f"{BASE}/{appointed['id']}")
        author = _make_user(
            db_session,
            UserRole.USER,
            "author@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        post = self._post_in_the_sephardic_widows_cell(db_session, author)
        as_user(author)

        await self._report_the_post(client, post)

        assert sent_alerts == []
