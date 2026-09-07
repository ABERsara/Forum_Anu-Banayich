"""
Unit tests for agent_service.

The catalog half (get_visible_domains, ABF-120) is the first section; the
conversation half (ABF-122) follows from TestGetVisibleDomain onwards.

test_agent_chat.py drives the ABF-122 code through the HTTP routes. What is
here instead are the decisions that are awkward to reach from a request,
because each one needs rows planted at a particular time or a particular
shape:

  - **The single-domain IDOR guard.** get_visible_domain() answers one 404 for
    four different reasons, and an ADMIN reaches a domain no member can.
  - **The quota window.** messages_left_today() counts a rolling 24 hours, so
    what matters is a message that has just aged out of it — and no endpoint
    can write a message dated yesterday.
  - **The history window.** _recent_turns() takes the newest turns, in the
    order they were said, decrypted, with the fixed disclaimer taken back off.
  - **The retrieval fallback.** _retrieve_for() widens a follow-up with the
    question before it, but only when the follow-up found nothing itself.

The DB is real (in-memory), per CONTRIBUTING §9.
"""

import base64
import os
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    AgentMessageRole,
    GroupVisibility,
    ProfessionalDomain,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.encryption import encrypt_message
from app.models.agent import (
    AgentConversation,
    AgentDomain,
    AgentKnowledgeEntry,
    AgentMessage,
)
from app.models.user import User
from app.services import agent_service, llm_service


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


# ===========================================================================
# ABF-122 — the conversation flow
# ===========================================================================

HOUSING_TITLE = "סיוע בדיור למשפחות חד-הוריות"
HOUSING_QUESTION = "האם מגיע לי סיוע בדיור?"
PRONOUN_FOLLOW_UP = "וכמה זה בערך?"


@pytest.fixture
def member(db_session: Session) -> User:
    return _make_user(
        db_session,
        email="asker@example.com",
        user_type=UserType.WIDOW,
        sector=Sector.HASIDIC,
    )


@pytest.fixture
def domain(db_session: Session) -> AgentDomain:
    return _make_domain(db_session, "הסוכן")


@pytest.fixture
def conversation(
    db_session: Session, member: User, domain: AgentDomain
) -> AgentConversation:
    row = AgentConversation(user_id=member.id, domain_id=domain.id)
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture
def housing_entry(db_session: Session, domain: AgentDomain) -> AgentKnowledgeEntry:
    entry = AgentKnowledgeEntry(
        domain_id=domain.id,
        title=HOUSING_TITLE,
        content="משפחה חד-הורית זכאית לסיוע בשכר דירה בכפוף למבחן הכנסה.",
        source_name="נוהל סיוע בשכר דירה",
        updated_by=_make_user(db_session, email="staff@example.com").id,
    )
    db_session.add(entry)
    db_session.commit()
    return entry


def _say(
    db_session: Session,
    conversation: AgentConversation,
    role: AgentMessageRole,
    content: str,
    minutes_ago: float = 0,
) -> AgentMessage:
    """Write one turn — encrypted, as the service does — optionally backdated."""
    ciphertext, key_version = encrypt_message(content)
    message = AgentMessage(
        conversation_id=conversation.id,
        role=role,
        content=ciphertext,
        key_version=key_version,
        created_at=agent_service._utc_now() - timedelta(minutes=minutes_ago),
    )
    db_session.add(message)
    db_session.commit()
    return message


# ---------------------------------------------------------------------------
# get_visible_domain() — the IDOR guard
# ---------------------------------------------------------------------------


class TestGetVisibleDomain:
    """One agent by id. ABF-120 shipped only the plural form; without this a
    `{domain_id}` in a URL would be trusted exactly as it arrived."""

    def test_returns_a_domain_the_member_may_use(
        self, db_session: Session, member: User
    ) -> None:
        row = _make_domain(
            db_session, "mine", GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        assert agent_service.get_visible_domain(db_session, member, row.id).id == row.id

    @pytest.mark.parametrize(
        ("group", "sector", "is_active"),
        [
            (GroupVisibility.ORPHANS_MALE, SectorVisibility.ALL, True),
            (GroupVisibility.ALL, SectorVisibility.SEPHARDIC, True),
            (GroupVisibility.ALL, SectorVisibility.ALL, False),
        ],
        ids=["another-group", "another-sector", "deactivated"],
    )
    def test_a_domain_the_member_may_not_use_is_404(
        self, db_session: Session, member: User, group, sector, is_active
    ) -> None:
        row = _make_domain(db_session, "not-mine", group, sector, is_active=is_active)

        with pytest.raises(HTTPException) as exc:
            agent_service.get_visible_domain(db_session, member, row.id)

        assert exc.value.status_code == 404

    def test_an_id_that_does_not_exist_is_the_same_404(
        self, db_session: Session, member: User
    ) -> None:
        """The point of the guard: "no such agent" and "an agent for another
        group" have to be indistinguishable, or the status pair becomes a way
        to enumerate which agents exist for which sector."""
        hidden = _make_domain(
            db_session, "hidden", GroupVisibility.ORPHANS_MALE, SectorVisibility.ALL
        )

        with pytest.raises(HTTPException) as for_hidden:
            agent_service.get_visible_domain(db_session, member, hidden.id)
        with pytest.raises(HTTPException) as for_missing:
            agent_service.get_visible_domain(db_session, member, "no-such-domain")

        assert for_hidden.value.status_code == for_missing.value.status_code == 404
        assert for_hidden.value.detail == for_missing.value.detail

    def test_an_admin_reaches_a_domain_no_member_of_that_group_could(
        self, db_session: Session
    ) -> None:
        """The audit trail is admin-visible and points at conversations; an
        admin has no user_type/sector to be filtered by."""
        admin = _make_user(
            db_session,
            email="admin@example.com",
            user_type=None,
            sector=None,
            role=UserRole.ADMIN,
        )
        row = _make_domain(
            db_session,
            "orphans",
            GroupVisibility.ORPHANS_MALE,
            SectorVisibility.HASIDIC,
        )

        assert agent_service.get_visible_domain(db_session, admin, row.id).id == row.id

    def test_an_admin_reaches_a_deactivated_domain_too(
        self, db_session: Session
    ) -> None:
        """An AuditLog row pointing into a since-retired agent still has to open."""
        admin = _make_user(
            db_session,
            email="admin@example.com",
            user_type=None,
            sector=None,
            role=UserRole.ADMIN,
        )
        row = _make_domain(db_session, "retired", is_active=False)

        assert agent_service.get_visible_domain(db_session, admin, row.id).id == row.id

    @pytest.mark.parametrize("role", [UserRole.MODERATOR, UserRole.PROFESSIONAL])
    def test_other_staff_roles_get_the_same_404_as_a_stranger(
        self, db_session: Session, role: UserRole
    ) -> None:
        """Not a 500 from the missing user_type, and not access either: a
        moderator has no business inside a member's agent thread (SPEC §9.3)."""
        actor = _make_user(
            db_session,
            email=f"{role.value}@example.com",
            user_type=None,
            sector=None,
            role=role,
        )
        row = _make_domain(db_session, "open-to-members")

        with pytest.raises(HTTPException) as exc:
            agent_service.get_visible_domain(db_session, actor, row.id)

        assert exc.value.status_code == 404

    def test_a_member_row_without_group_or_sector_is_404_not_a_crash(
        self, db_session: Session
    ) -> None:
        """USER rows always carry both today; if one ever did not, building the
        filter would raise ValueError and surface as a 500."""
        broken = _make_user(
            db_session, email="broken@example.com", user_type=None, sector=None
        )
        row = _make_domain(db_session, "open-to-members")

        with pytest.raises(HTTPException) as exc:
            agent_service.get_visible_domain(db_session, broken, row.id)

        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# messages_left_today()
# ---------------------------------------------------------------------------


class TestMessagesLeftToday:
    def test_an_untouched_quota_is_the_configured_one(
        self, db_session: Session, member: User
    ) -> None:
        assert agent_service.messages_left_today(db_session, member) == (
            settings.AGENT_RATE_LIMIT_PER_DAY
        )

    def test_each_question_spends_one(
        self, db_session: Session, member: User, conversation: AgentConversation
    ) -> None:
        _say(db_session, conversation, AgentMessageRole.USER, "question")

        assert agent_service.messages_left_today(db_session, member) == (
            settings.AGENT_RATE_LIMIT_PER_DAY - 1
        )

    def test_the_agents_own_replies_are_free(
        self, db_session: Session, member: User, conversation: AgentConversation
    ) -> None:
        """Two rows are written per exchange; counting both would silently
        halve the quota the user was promised."""
        _say(db_session, conversation, AgentMessageRole.AGENT, "answer")

        assert agent_service.messages_left_today(db_session, member) == (
            settings.AGENT_RATE_LIMIT_PER_DAY
        )

    def test_a_message_just_inside_the_window_still_counts(
        self, db_session: Session, member: User, conversation: AgentConversation
    ) -> None:
        _say(
            db_session,
            conversation,
            AgentMessageRole.USER,
            "question",
            minutes_ago=23 * 60,
        )

        assert agent_service.messages_left_today(db_session, member) == (
            settings.AGENT_RATE_LIMIT_PER_DAY - 1
        )

    def test_a_message_that_has_aged_out_does_not(
        self, db_session: Session, member: User, conversation: AgentConversation
    ) -> None:
        """The window rolls rather than resetting at midnight — which is what
        stops a user spending two days' budget either side of it."""
        _say(
            db_session,
            conversation,
            AgentMessageRole.USER,
            "question",
            minutes_ago=25 * 60,
        )

        assert agent_service.messages_left_today(db_session, member) == (
            settings.AGENT_RATE_LIMIT_PER_DAY
        )

    def test_another_users_questions_are_not_counted(
        self, db_session: Session, member: User, conversation: AgentConversation
    ) -> None:
        _say(db_session, conversation, AgentMessageRole.USER, "question")
        other = _make_user(db_session, email="other@example.com")

        assert agent_service.messages_left_today(db_session, other) == (
            settings.AGENT_RATE_LIMIT_PER_DAY
        )

    def test_the_quota_is_shared_across_every_agent(
        self, db_session: Session, member: User, domain: AgentDomain
    ) -> None:
        """The cost being capped is one provider bill, not one agent's — so a
        second domain does not hand the member a second allowance."""
        other_domain = _make_domain(db_session, "second agent")
        for target in (domain, other_domain):
            row = AgentConversation(user_id=member.id, domain_id=target.id)
            db_session.add(row)
            db_session.commit()
            _say(db_session, row, AgentMessageRole.USER, "question")

        assert agent_service.messages_left_today(db_session, member) == (
            settings.AGENT_RATE_LIMIT_PER_DAY - 2
        )

    def test_the_quota_never_reads_as_negative(
        self,
        db_session: Session,
        monkeypatch,
        member: User,
        conversation: AgentConversation,
    ) -> None:
        monkeypatch.setattr(settings, "AGENT_RATE_LIMIT_PER_DAY", 1)
        _say(db_session, conversation, AgentMessageRole.USER, "one")
        _say(db_session, conversation, AgentMessageRole.USER, "two")

        assert agent_service.messages_left_today(db_session, member) == 0


# ---------------------------------------------------------------------------
# _recent_turns()
# ---------------------------------------------------------------------------


class TestRecentTurns:
    def test_a_conversation_that_has_not_started_has_no_history(
        self, db_session: Session
    ) -> None:
        assert agent_service._recent_turns(db_session, None) == []

    def test_turns_come_back_oldest_first_and_decrypted(
        self, db_session: Session, conversation: AgentConversation
    ) -> None:
        """Stored rows are ciphertext; what a prompt gets is plaintext."""
        first = _say(
            db_session, conversation, AgentMessageRole.USER, "first", minutes_ago=2
        )
        _say(db_session, conversation, AgentMessageRole.AGENT, "answer", minutes_ago=1)

        history = agent_service._recent_turns(db_session, conversation)

        assert first.content != "first"  # the stored row really is encrypted
        assert [turn.content for turn in history] == ["first", "answer"]
        assert history[0].role == AgentMessageRole.USER

    def test_only_the_newest_turns_survive_the_cap(
        self, db_session: Session, monkeypatch, conversation: AgentConversation
    ) -> None:
        """A turn is a question and its answer, so N turns is up to 2N rows."""
        monkeypatch.setattr(settings, "AGENT_HISTORY_TURNS", 1)
        _say(db_session, conversation, AgentMessageRole.USER, "old-q", minutes_ago=4)
        _say(db_session, conversation, AgentMessageRole.AGENT, "old-a", minutes_ago=3)
        _say(db_session, conversation, AgentMessageRole.USER, "new-q", minutes_ago=2)
        _say(db_session, conversation, AgentMessageRole.AGENT, "new-a", minutes_ago=1)

        history = agent_service._recent_turns(db_session, conversation)

        assert [turn.content for turn in history] == ["new-q", "new-a"]

    def test_history_can_be_switched_off_entirely(
        self, db_session: Session, monkeypatch, conversation: AgentConversation
    ) -> None:
        monkeypatch.setattr(settings, "AGENT_HISTORY_TURNS", 0)
        _say(db_session, conversation, AgentMessageRole.USER, "question")

        assert agent_service._recent_turns(db_session, conversation) == []

    def test_the_disclaimer_does_not_go_back_into_the_prompt(
        self, db_session: Session, conversation: AgentConversation
    ) -> None:
        stored = (
            f"answer{agent_service.DISCLAIMER_SEPARATOR}{llm_service.ANSWER_DISCLAIMER}"
        )
        _say(db_session, conversation, AgentMessageRole.AGENT, stored)

        (turn,) = agent_service._recent_turns(db_session, conversation)

        assert turn.content == "answer"

    def test_a_disclaimer_quoted_mid_answer_is_left_alone(self) -> None:
        """Only the paragraph _compose_answer() appended comes off — matched as
        a suffix, so an answer that happens to mention it keeps its text."""
        quoted = f"{llm_service.ANSWER_DISCLAIMER} — וזה מה שכתוב בהמשך."

        assert agent_service._without_disclaimer(quoted) == quoted


# ---------------------------------------------------------------------------
# _retrieve_for()
# ---------------------------------------------------------------------------


class TestRetrieveFor:
    def test_a_question_that_stands_alone_is_searched_as_written(
        self, db_session: Session, domain: AgentDomain, housing_entry
    ) -> None:
        entries = agent_service._retrieve_for(db_session, domain, HOUSING_QUESTION, [])

        assert [entry.title for entry in entries] == [HOUSING_TITLE]

    def test_a_follow_up_borrows_the_words_of_the_question_before_it(
        self, db_session: Session, domain: AgentDomain, housing_entry
    ) -> None:
        history = [
            llm_service.HistoryTurn(
                role=AgentMessageRole.USER, content=HOUSING_QUESTION
            ),
            llm_service.HistoryTurn(role=AgentMessageRole.AGENT, content="כן, בתנאים."),
        ]

        entries = agent_service._retrieve_for(
            db_session, domain, PRONOUN_FOLLOW_UP, history
        )

        assert [entry.title for entry in entries] == [HOUSING_TITLE]

    def test_with_nothing_behind_it_a_bare_follow_up_finds_nothing(
        self, db_session: Session, domain: AgentDomain, housing_entry
    ) -> None:
        """The widening is a fallback for a follow-up, not a second attempt for
        every question: an opening message has nothing to widen with."""
        assert (
            agent_service._retrieve_for(db_session, domain, PRONOUN_FOLLOW_UP, []) == []
        )

    def test_only_the_users_own_words_are_borrowed(
        self, db_session: Session, domain: AgentDomain, housing_entry
    ) -> None:
        """The agent's replies are its words, not a statement of what is being
        asked about — widening with them would search the answer, not the
        question."""
        history = [
            llm_service.HistoryTurn(
                role=AgentMessageRole.AGENT, content=f"לפי {HOUSING_TITLE}, כן."
            )
        ]

        assert (
            agent_service._retrieve_for(db_session, domain, PRONOUN_FOLLOW_UP, history)
            == []
        )

    def test_never_reads_another_agents_knowledge_base(
        self, db_session: Session, domain: AgentDomain, housing_entry
    ) -> None:
        """SPEC §12.1: each agent is confined to its own material, and that is
        enforced in the query rather than asked for in the prompt."""
        other_domain = _make_domain(db_session, "second agent")

        assert (
            agent_service._retrieve_for(db_session, other_domain, HOUSING_QUESTION, [])
            == []
        )


# ---------------------------------------------------------------------------
# _plaintext()
# ---------------------------------------------------------------------------


class TestDecryption:
    def test_a_row_that_fails_authentication_is_a_generic_500(
        self, db_session: Session, conversation: AgentConversation
    ) -> None:
        """AES-GCM authenticates as well as encrypts, so a tampered or
        corrupted row is caught rather than decoded into garbage. What the
        caller learns is only that the server failed — not that it failed
        *decrypting*, which would tell an attacker their edit landed.

        Base64 that decodes cleanly but authenticates as nothing: this is the
        InvalidTag path, not a malformed-input path.
        """
        message = _say(db_session, conversation, AgentMessageRole.AGENT, "answer")
        message.content = base64.b64encode(os.urandom(48)).decode("ascii")
        db_session.commit()

        with pytest.raises(HTTPException) as exc:
            agent_service._plaintext(message)

        assert exc.value.status_code == 500
        assert exc.value.detail == "errors.internal_server_error"
        assert "decrypt" not in str(exc.value.detail).lower()

    def test_a_readable_row_round_trips(
        self, db_session: Session, conversation: AgentConversation
    ) -> None:
        message = _say(
            db_session, conversation, AgentMessageRole.USER, HOUSING_QUESTION
        )

        assert agent_service._plaintext(message) == HOUSING_QUESTION
