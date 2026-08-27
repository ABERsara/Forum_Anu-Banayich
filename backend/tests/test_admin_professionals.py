"""
Integration tests for the /admin/professionals endpoints (professional catalog).
"""

from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.constants import (
    AccountStatus,
    AuditAction,
    ProfessionalDomain,
    Sector,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.user import User

BASE = "/api/v1/admin/professionals"


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


def _make_professional(db_session: Session, email: str, **kwargs: Any) -> User:
    defaults: dict[str, Any] = {
        "professional_domain": ProfessionalDomain.LAWYER,
        "professional_groups": ["all"],
        "professional_sectors": ["all"],
        "professional_description": "desc",
        "is_active_professional": True,
    }
    defaults.update(kwargs)
    return _make_user(db_session, UserRole.PROFESSIONAL, email, **defaults)


def _create_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "first_name": "ישראל",
        "last_name": "כהן",
        "email": "cohen.law@example.com",
        "phone": "0501234567",
        "professional_domain": ProfessionalDomain.LAWYER,
        "professional_groups": ["widow"],
        "professional_sectors": ["hasidic"],
        "professional_description": "עורך דין לענייני ירושה",
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


class TestListProfessionals:
    async def test_returns_every_professional_with_their_catalog_fields(
        self, client, db_session, as_user, admin
    ) -> None:
        as_user(admin)
        _make_professional(
            db_session,
            "pro@example.com",
            professional_groups=["widow", "orphan_female"],
            professional_sectors=["hasidic"],
        )

        response = await client.get(BASE)

        assert response.status_code == 200
        [professional] = response.json()
        assert professional["professional_domain"] == ProfessionalDomain.LAWYER
        assert professional["professional_groups"] == ["widow", "orphan_female"]
        assert professional["professional_sectors"] == ["hasidic"]
        assert professional["professional_description"] == "desc"
        assert professional["is_active_professional"] is True
        assert professional["email"] == "pro@example.com"

    async def test_includes_deactivated_professionals(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_professional(
            db_session, "hidden@example.com", is_active_professional=False
        )
        as_user(admin)

        response = await client.get(BASE)

        assert response.status_code == 200
        assert [p["email"] for p in response.json()] == ["hidden@example.com"]

    async def test_excludes_users_who_are_not_professionals(
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

    async def test_reads_null_group_and_sector_columns_as_empty_lists(
        self, client, db_session, as_user, admin
    ) -> None:
        """Rows predating the catalog hold NULL; the contract is always a list."""
        _make_professional(
            db_session,
            "legacy@example.com",
            professional_groups=None,
            professional_sectors=None,
        )
        as_user(admin)

        response = await client.get(BASE)

        [professional] = response.json()
        assert professional["professional_groups"] == []
        assert professional["professional_sectors"] == []

    async def test_requires_authentication(self, client) -> None:
        response = await client.get(BASE)

        assert response.status_code == 401

    async def test_forbidden_for_non_admin_roles(
        self, client, db_session, as_user
    ) -> None:
        professional = _make_professional(db_session, "pro@example.com")
        as_user(professional)

        response = await client.get(BASE)

        assert response.status_code == 403


class TestAddProfessional:
    async def test_creates_and_returns_the_new_professional(
        self, client, db_session, as_user, admin
    ) -> None:
        as_user(admin)

        response = await client.post(BASE, json=_create_body())

        assert response.status_code == 201
        body = response.json()
        assert body["id"]
        assert body["first_name"] == "ישראל"
        assert body["role"] == UserRole.PROFESSIONAL
        assert body["account_status"] == AccountStatus.ACTIVE
        assert body["professional_domain"] == ProfessionalDomain.LAWYER
        assert body["professional_groups"] == ["widow"]
        assert body["is_active_professional"] is True

    async def test_the_new_professional_is_listed_in_the_catalog(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)
        created = (await client.post(BASE, json=_create_body())).json()

        response = await client.get(BASE)

        assert [p["id"] for p in response.json()] == [created["id"]]

    async def test_records_the_addition_in_the_audit_log(
        self, client, db_session, as_user, admin
    ) -> None:
        as_user(admin)

        created = (await client.post(BASE, json=_create_body())).json()

        log = (
            db_session.query(AuditLog).filter(AuditLog.entity_id == created["id"]).one()
        )
        assert log.action == AuditAction.PROFESSIONAL_ADDED
        assert log.actor_id == admin.id

    async def test_rejects_an_email_already_registered(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_professional(db_session, "taken@example.com")
        as_user(admin)

        response = await client.post(BASE, json=_create_body(email="taken@example.com"))

        assert response.status_code == 409

    @pytest.mark.parametrize(
        "invalid",
        [
            pytest.param({"professional_groups": []}, id="no_groups"),
            pytest.param({"professional_sectors": []}, id="no_sectors"),
            pytest.param({"professional_groups": ["nobody"]}, id="unknown_group"),
            pytest.param({"professional_sectors": ["mars"]}, id="unknown_sector"),
            pytest.param({"professional_domain": "astrologer"}, id="unknown_domain"),
            pytest.param({"professional_domain": None}, id="missing_domain"),
            pytest.param({"email": "not-an-email"}, id="malformed_email"),
            pytest.param({"first_name": "א"}, id="too_short_name"),
            pytest.param(
                {"professional_description": "x" * 501}, id="long_description"
            ),
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
        professional = _make_professional(db_session, "pro@example.com")
        as_user(professional)

        response = await client.post(BASE, json=_create_body())

        assert response.status_code == 403


class TestUpdateProfessional:
    async def test_updates_the_catalog_fields(
        self, client, db_session, as_user, admin
    ) -> None:
        professional = _make_professional(
            db_session,
            "pro@example.com",
            professional_groups=["widower"],
            professional_sectors=["litvish"],
        )
        as_user(admin)

        response = await client.put(
            f"{BASE}/{professional.id}",
            json={
                "professional_domain": ProfessionalDomain.PSYCHOLOGIST,
                "professional_groups": ["widow"],
                "professional_sectors": ["hasidic", "sephardic"],
                "professional_description": "מטפלת בטראומה",
                "is_active_professional": False,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["professional_domain"] == ProfessionalDomain.PSYCHOLOGIST
        assert body["professional_groups"] == ["widow"]
        assert body["professional_sectors"] == ["hasidic", "sephardic"]
        assert body["professional_description"] == "מטפלת בטראומה"
        assert body["is_active_professional"] is False

    async def test_toggling_the_active_flag_keeps_the_rest_of_the_profile(
        self, client, db_session, as_user, admin
    ) -> None:
        professional = _make_professional(db_session, "pro@example.com")
        as_user(admin)

        response = await client.put(
            f"{BASE}/{professional.id}", json={"is_active_professional": False}
        )

        body = response.json()
        assert body["is_active_professional"] is False
        assert body["professional_description"] == "desc"
        assert body["professional_domain"] == ProfessionalDomain.LAWYER

    async def test_records_the_update_in_the_audit_log(
        self, client, db_session, as_user, admin
    ) -> None:
        professional = _make_professional(db_session, "pro@example.com")
        as_user(admin)

        await client.put(
            f"{BASE}/{professional.id}", json={"is_active_professional": False}
        )

        log = (
            db_session.query(AuditLog)
            .filter(AuditLog.entity_id == professional.id)
            .one()
        )
        assert log.action == AuditAction.PROFESSIONAL_UPDATED
        assert log.actor_id == admin.id
        assert log.details == {
            "updated_fields": ["is_active_professional"],
            "is_active_professional": False,
        }

    async def test_unknown_professional_returns_404(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        response = await client.put(
            f"{BASE}/does-not-exist", json={"is_active_professional": False}
        )

        assert response.status_code == 404

    async def test_cannot_edit_a_user_who_is_not_a_professional(
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

        response = await client.put(
            f"{BASE}/{member.id}",
            json={"professional_domain": ProfessionalDomain.RABBI},
        )

        assert response.status_code == 400

    @pytest.mark.parametrize(
        "field",
        [
            "professional_domain",
            "professional_groups",
            "professional_sectors",
            "is_active_professional",
        ],
    )
    async def test_rejects_an_explicit_null_that_would_unlist_the_professional(
        self, client, db_session, as_user, admin, field: str
    ) -> None:
        professional = _make_professional(db_session, "pro@example.com")
        as_user(admin)

        response = await client.put(f"{BASE}/{professional.id}", json={field: None})

        assert response.status_code == 422

    async def test_clearing_the_description_is_allowed(
        self, client, db_session, as_user, admin
    ) -> None:
        professional = _make_professional(db_session, "pro@example.com")
        as_user(admin)

        response = await client.put(
            f"{BASE}/{professional.id}", json={"professional_description": None}
        )

        assert response.status_code == 200
        assert response.json()["professional_description"] is None

    async def test_forbidden_for_non_admin_roles(
        self, client, db_session, as_user
    ) -> None:
        professional = _make_professional(db_session, "pro@example.com")
        as_user(professional)

        response = await client.put(
            f"{BASE}/{professional.id}", json={"is_active_professional": False}
        )

        assert response.status_code == 403
