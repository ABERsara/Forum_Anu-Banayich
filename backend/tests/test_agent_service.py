"""
Unit tests for agent_service.get_visible_domains().
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
from app.models.agent import AgentDomain
from app.models.user import User
from app.services import agent_service


def _make_domain(
    db_session: Session,
    name: str,
    group_visibility: GroupVisibility = GroupVisibility.ALL,
    sector_visibility: SectorVisibility = SectorVisibility.ALL,
    *,
    is_active: bool = True,
    professional_domain: ProfessionalDomain = ProfessionalDomain.SOCIAL_WORKER,
) -> AgentDomain:
    domain = AgentDomain(
        name=name,
        description=f"תיאור עבור {name}",
        group_visibility=group_visibility,
        sector_visibility=sector_visibility,
        professional_domain=professional_domain,
        is_active=is_active,
    )
    db_session.add(domain)
    db_session.commit()
    return domain


def _make_user(
    db_session: Session,
    email: str = "member@example.com",
    user_type: UserType | None = UserType.WIDOW,
    sector: Sector | None = Sector.SEPHARDIC,
    role: UserRole = UserRole.USER,
) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="Member",
        role=role,
        user_type=user_type,
        sector=sector,
    )
    db_session.add(user)
    db_session.commit()
    return user


class TestGroupSectorMatching:
    def test_returns_domain_matching_group_and_sector_exactly(
        self, db_session: Session
    ) -> None:
        user = _make_user(db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC)
        _make_domain(
            db_session, "match", GroupVisibility.WIDOWS, SectorVisibility.SEPHARDIC
        )

        result = agent_service.get_visible_domains(db_session, user)

        assert [d.name for d in result] == ["match"]

    def test_returns_domain_open_to_all_groups_and_sectors(
        self, db_session: Session
    ) -> None:
        user = _make_user(db_session)
        _make_domain(db_session, "broadcast", GroupVisibility.ALL, SectorVisibility.ALL)

        result = agent_service.get_visible_domains(db_session, user)

        assert [d.name for d in result] == ["broadcast"]

    def test_returns_domain_when_group_matches_and_sector_is_all(
        self, db_session: Session
    ) -> None:
        user = _make_user(db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC)
        _make_domain(
            db_session, "widows-any", GroupVisibility.WIDOWS, SectorVisibility.ALL
        )

        result = agent_service.get_visible_domains(db_session, user)

        assert [d.name for d in result] == ["widows-any"]

    def test_returns_domain_when_sector_matches_and_group_is_all(
        self, db_session: Session
    ) -> None:
        user = _make_user(db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC)
        _make_domain(
            db_session, "any-sephardic", GroupVisibility.ALL, SectorVisibility.SEPHARDIC
        )

        result = agent_service.get_visible_domains(db_session, user)

        assert [d.name for d in result] == ["any-sephardic"]

    def test_excludes_domain_of_a_different_group(self, db_session: Session) -> None:
        user = _make_user(db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC)
        _make_domain(
            db_session, "orphans", GroupVisibility.ORPHANS_MALE, SectorVisibility.ALL
        )

        assert agent_service.get_visible_domains(db_session, user) == []

    def test_excludes_domain_of_a_different_sector(self, db_session: Session) -> None:
        user = _make_user(db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC)
        _make_domain(
            db_session, "hasidic", GroupVisibility.ALL, SectorVisibility.HASIDIC
        )

        assert agent_service.get_visible_domains(db_session, user) == []

    def test_excludes_domain_when_group_matches_but_sector_does_not(
        self, db_session: Session
    ) -> None:
        # AND, not OR: a group hit alone is not enough.
        user = _make_user(db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC)
        _make_domain(
            db_session,
            "widows-hasidic",
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
        )

        assert agent_service.get_visible_domains(db_session, user) == []

    def test_excludes_domain_when_sector_matches_but_group_does_not(
        self, db_session: Session
    ) -> None:
        user = _make_user(db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC)
        _make_domain(
            db_session,
            "orphans-sephardic",
            GroupVisibility.ORPHANS_MALE,
            SectorVisibility.SEPHARDIC,
        )

        assert agent_service.get_visible_domains(db_session, user) == []


class TestActiveFilter:
    def test_excludes_inactive_domain_even_when_otherwise_visible(
        self, db_session: Session
    ) -> None:
        user = _make_user(db_session)
        _make_domain(
            db_session,
            "disabled",
            GroupVisibility.ALL,
            SectorVisibility.ALL,
            is_active=False,
        )

        assert agent_service.get_visible_domains(db_session, user) == []

    def test_returns_active_and_hides_inactive_side_by_side(
        self, db_session: Session
    ) -> None:
        user = _make_user(db_session)
        _make_domain(db_session, "on", GroupVisibility.ALL, SectorVisibility.ALL)
        _make_domain(
            db_session,
            "off",
            GroupVisibility.ALL,
            SectorVisibility.ALL,
            is_active=False,
        )

        result = agent_service.get_visible_domains(db_session, user)

        assert [d.name for d in result] == ["on"]


class TestOrderingAndShape:
    def test_orders_domains_by_name_case_insensitively(
        self, db_session: Session
    ) -> None:
        user = _make_user(db_session)
        for name in ("Banana", "apple", "Cherry"):
            _make_domain(db_session, name)

        result = agent_service.get_visible_domains(db_session, user)

        # Case-insensitive: apple, Banana, Cherry. A raw binary sort (SQLite's
        # default) would put the capitalised names before "apple".
        assert [d.name for d in result] == ["apple", "Banana", "Cherry"]

    def test_returns_orm_model_instances(self, db_session: Session) -> None:
        user = _make_user(db_session)
        _make_domain(db_session, "d")

        result = agent_service.get_visible_domains(db_session, user)

        assert isinstance(result[0], AgentDomain)

    def test_returns_empty_list_when_no_domains_exist(
        self, db_session: Session
    ) -> None:
        user = _make_user(db_session)

        assert agent_service.get_visible_domains(db_session, user) == []


class TestDifferentUsers:
    def test_users_of_different_group_and_sector_see_different_domains(
        self, db_session: Session
    ) -> None:
        widow = _make_user(
            db_session,
            email="widow@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        orphan = _make_user(
            db_session,
            email="orphan@example.com",
            user_type=UserType.ORPHAN_MALE,
            sector=Sector.HASIDIC,
        )
        _make_domain(
            db_session,
            "for-widows",
            GroupVisibility.WIDOWS,
            SectorVisibility.SEPHARDIC,
        )
        _make_domain(
            db_session,
            "for-orphans",
            GroupVisibility.ORPHANS_MALE,
            SectorVisibility.HASIDIC,
        )
        _make_domain(
            db_session, "for-everyone", GroupVisibility.ALL, SectorVisibility.ALL
        )

        widow_seen = {
            d.name for d in agent_service.get_visible_domains(db_session, widow)
        }
        orphan_seen = {
            d.name for d in agent_service.get_visible_domains(db_session, orphan)
        }

        assert widow_seen == {"for-widows", "for-everyone"}
        assert orphan_seen == {"for-orphans", "for-everyone"}


class TestVisibilityEnumMapping:
    """get_visible_domains() does GroupVisibility(user.user_type.value) and
    SectorVisibility(user.sector.value). A UserType/Sector member whose value
    has no matching visibility member would raise ValueError -> 500. Pin that
    the mappings are total across every enum member."""

    @pytest.mark.parametrize("user_type", list(UserType))
    def test_every_user_type_maps_to_a_group_visibility(
        self, user_type: UserType
    ) -> None:
        # constructing must not raise, and the string value must survive the
        # round-trip (the two enums share their .value strings).
        assert GroupVisibility(user_type.value).value == user_type.value

    @pytest.mark.parametrize("sector", list(Sector))
    def test_every_sector_maps_to_a_sector_visibility(self, sector: Sector) -> None:
        assert SectorVisibility(sector.value).value == sector.value


class TestFullGroupMatrix:
    @pytest.mark.parametrize("user_type", list(UserType))
    def test_group_specific_domain_is_visible_only_to_its_own_group(
        self, db_session: Session, user_type: UserType
    ) -> None:
        user = _make_user(
            db_session,
            email=f"{user_type.value}@example.com",
            user_type=user_type,
            sector=Sector.GENERAL,
        )
        own = GroupVisibility(user_type.value)
        other = next(g for g in GroupVisibility if g not in (own, GroupVisibility.ALL))
        _make_domain(db_session, "mine", own, SectorVisibility.ALL)
        _make_domain(db_session, "not-mine", other, SectorVisibility.ALL)

        result = agent_service.get_visible_domains(db_session, user)

        assert [d.name for d in result] == ["mine"]

    @pytest.mark.parametrize("sector", list(Sector))
    def test_sector_specific_domain_is_visible_only_to_its_own_sector(
        self, db_session: Session, sector: Sector
    ) -> None:
        user = _make_user(
            db_session,
            email=f"{sector.value}@example.com",
            user_type=UserType.WIDOWER,
            sector=sector,
        )
        own = SectorVisibility(sector.value)
        other = next(
            s for s in SectorVisibility if s not in (own, SectorVisibility.ALL)
        )
        _make_domain(db_session, "mine", GroupVisibility.ALL, own)
        _make_domain(db_session, "not-mine", GroupVisibility.ALL, other)

        result = agent_service.get_visible_domains(db_session, user)

        assert [d.name for d in result] == ["mine"]


class TestPrecondition:
    def test_raises_when_user_has_no_group_or_sector(self, db_session: Session) -> None:
        # get_visible_domains relies on the endpoint's require_role(USER) gate;
        # being called with a role that has no user_type/sector is a bug.
        admin = _make_user(
            db_session,
            email="admin@example.com",
            user_type=None,
            sector=None,
            role=UserRole.ADMIN,
        )

        with pytest.raises(ValueError):
            agent_service.get_visible_domains(db_session, admin)
