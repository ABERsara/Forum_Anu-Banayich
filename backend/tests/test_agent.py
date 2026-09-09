"""
Integration tests for GET /agents.
"""

import pytest
from sqlalchemy.orm import Session

from app.core.constants import (
    GroupVisibility,
    ProfessionalDomain,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.agent import AgentDomain
from app.models.user import User

BASE = "/api/v1/agents"


@pytest.fixture
def as_user():
    """Override get_current_user and get_current_active_user to return the given user."""

    def _apply(user: User) -> None:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


def _make_domain(
    db_session: Session,
    name: str,
    group_visibility: GroupVisibility = GroupVisibility.ALL,
    sector_visibility: SectorVisibility = SectorVisibility.ALL,
    *,
    is_active: bool = True,
) -> AgentDomain:
    domain = AgentDomain(
        name=name,
        description=f"תיאור עבור {name}",
        group_visibility=group_visibility,
        sector_visibility=sector_visibility,
        professional_domain=ProfessionalDomain.SOCIAL_WORKER,
        is_active=is_active,
    )
    db_session.add(domain)
    db_session.commit()
    return domain


def _make_user(
    db_session: Session,
    email: str,
    role: UserRole = UserRole.USER,
    user_type: UserType | None = UserType.WIDOW,
    sector: Sector | None = Sector.SEPHARDIC,
) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        user_type=user_type,
        sector=sector,
    )
    db_session.add(user)
    db_session.commit()
    return user


class TestListAgentDomains:
    async def test_returns_only_domains_visible_to_the_user(
        self, client, db_session: Session, as_user
    ) -> None:
        user = _make_user(
            db_session,
            "widow@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        _make_domain(
            db_session, "for widows", GroupVisibility.WIDOWS, SectorVisibility.ALL
        )
        _make_domain(
            db_session,
            "for orphans",
            GroupVisibility.ORPHANS_MALE,
            SectorVisibility.ALL,
        )
        as_user(user)

        response = await client.get(BASE)

        assert response.status_code == 200
        assert [d["name"] for d in response.json()] == ["for widows"]

    async def test_domain_open_to_all_is_shown(
        self, client, db_session: Session, as_user
    ) -> None:
        user = _make_user(db_session, "widow@example.com")
        _make_domain(db_session, "everyone", GroupVisibility.ALL, SectorVisibility.ALL)
        as_user(user)

        response = await client.get(BASE)

        assert response.status_code == 200
        assert [d["name"] for d in response.json()] == ["everyone"]

    async def test_domain_of_another_group_is_hidden(
        self, client, db_session: Session, as_user
    ) -> None:
        user = _make_user(db_session, "widow@example.com", user_type=UserType.WIDOW)
        _make_domain(
            db_session,
            "orphans only",
            GroupVisibility.ORPHANS_MALE,
            SectorVisibility.ALL,
        )
        as_user(user)

        response = await client.get(BASE)

        assert response.status_code == 200
        assert response.json() == []

    async def test_group_match_but_sector_mismatch_is_hidden(
        self, client, db_session: Session, as_user
    ) -> None:
        # AND, not OR, end to end: a domain for the user's own group but a
        # different sector must not appear.
        user = _make_user(
            db_session,
            "widow@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        _make_domain(
            db_session,
            "widows hasidic",
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
        )
        as_user(user)

        response = await client.get(BASE)

        assert response.status_code == 200
        assert response.json() == []

    async def test_inactive_domain_is_hidden(
        self, client, db_session: Session, as_user
    ) -> None:
        user = _make_user(db_session, "widow@example.com")
        _make_domain(
            db_session,
            "disabled",
            GroupVisibility.ALL,
            SectorVisibility.ALL,
            is_active=False,
        )
        as_user(user)

        response = await client.get(BASE)

        assert response.status_code == 200
        assert response.json() == []

    async def test_response_items_expose_only_id_name_description(
        self, client, db_session: Session, as_user
    ) -> None:
        user = _make_user(db_session, "widow@example.com")
        _make_domain(db_session, "d", GroupVisibility.ALL, SectorVisibility.ALL)
        as_user(user)

        body = (await client.get(BASE)).json()

        assert set(body[0].keys()) == {"id", "name", "description"}

    async def test_domains_are_ordered_by_name(
        self, client, db_session: Session, as_user
    ) -> None:
        user = _make_user(db_session, "widow@example.com")
        for name in ("Zebra", "Alpha", "Mango"):
            _make_domain(db_session, name)
        as_user(user)

        body = (await client.get(BASE)).json()

        assert [d["name"] for d in body] == ["Alpha", "Mango", "Zebra"]

    async def test_returns_empty_list_when_nothing_visible(
        self, client, db_session: Session, as_user
    ) -> None:
        user = _make_user(db_session, "widow@example.com")
        as_user(user)

        response = await client.get(BASE)

        assert response.status_code == 200
        assert response.json() == []


class TestAuthentication:
    async def test_missing_token_returns_401(self, client) -> None:
        response = await client.get(BASE)
        assert response.status_code == 401

    async def test_invalid_token_returns_401(self, client) -> None:
        response = await client.get(
            BASE, headers={"Authorization": "Bearer not.a.valid.jwt"}
        )
        assert response.status_code == 401


class TestAuthorization:
    @pytest.mark.parametrize(
        "role",
        [UserRole.ADMIN, UserRole.MODERATOR, UserRole.PROFESSIONAL],
    )
    async def test_forbidden_for_non_user_roles(
        self, client, db_session: Session, as_user, role: UserRole
    ) -> None:
        actor = _make_user(
            db_session,
            f"{role.value}@example.com",
            role=role,
            user_type=None,
            sector=None,
        )
        as_user(actor)

        response = await client.get(BASE)

        assert response.status_code == 403
