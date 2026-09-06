"""
Unit tests for agent_service (ABF-122).

test_agent_chat.py drives the same code through the HTTP routes; this file
covers the three decisions that are awkward to reach from a request, because
each one needs rows planted at a particular time or a particular shape:

  - **The quota window.** messages_left_today() counts a rolling 24 hours, so
    what matters is a message that has just aged out of it — and no endpoint
    can write a message dated yesterday.
  - **The history window.** _recent_turns() takes the newest turns, in the
    order they were said, with the fixed disclaimer taken back off.
  - **The retrieval fallback.** _retrieve_for() widens a follow-up with the
    question before it, but only when the follow-up found nothing itself.

The DB is real (in-memory), per CONTRIBUTING §9.
"""

from datetime import timedelta

import pytest

from app.core.config import settings
from app.core.constants import (
    AccountStatus,
    AgentDomain,
    AgentMessageRole,
    Sector,
    UserType,
)
from app.models.agent import AgentConversation, AgentMessage
from app.models.agent_knowledge import AgentKnowledgeChunk
from app.services import agent_service, llm_service

DOMAIN = AgentDomain.SINGLE_PARENT_RIGHTS

HOUSING_TITLE = "סיוע בדיור למשפחות חד-הוריות"
HOUSING_QUESTION = "האם מגיע לי סיוע בדיור?"
PRONOUN_FOLLOW_UP = "וכמה זה בערך?"


@pytest.fixture
def user(make_user):
    return make_user(
        "asker@example.com",
        UserType.WIDOW,
        Sector.HASIDIC,
        account_status=AccountStatus.ACTIVE,
    )


@pytest.fixture
def conversation(db_session, user) -> AgentConversation:
    row = AgentConversation(user_id=user.id, domain=DOMAIN)
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture
def housing_chunk(db_session) -> AgentKnowledgeChunk:
    chunk = AgentKnowledgeChunk(
        domain=DOMAIN,
        title=HOUSING_TITLE,
        content="משפחה חד-הורית זכאית לסיוע בשכר דירה בכפוף למבחן הכנסה.",
        source="נוהל סיוע בשכר דירה",
    )
    db_session.add(chunk)
    db_session.commit()
    return chunk


def _say(
    db_session,
    conversation: AgentConversation,
    role: AgentMessageRole,
    content: str,
    minutes_ago: float = 0,
) -> AgentMessage:
    """Write one turn, optionally dated into the past."""
    message = AgentMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        created_at=agent_service._utc_now() - timedelta(minutes=minutes_ago),
    )
    db_session.add(message)
    db_session.commit()
    return message


# ---------------------------------------------------------------------------
# messages_left_today()
# ---------------------------------------------------------------------------


class TestMessagesLeftToday:
    def test_an_untouched_quota_is_the_configured_one(self, db_session, user):
        assert agent_service.messages_left_today(db_session, user) == (
            settings.AGENT_RATE_LIMIT_PER_DAY
        )

    def test_each_question_spends_one(self, db_session, user, conversation):
        _say(db_session, conversation, AgentMessageRole.USER, "שאלה")

        assert agent_service.messages_left_today(db_session, user) == (
            settings.AGENT_RATE_LIMIT_PER_DAY - 1
        )

    def test_the_agents_own_replies_are_free(self, db_session, user, conversation):
        """Two rows are written per exchange; counting both would silently
        halve the quota the user was promised."""
        _say(db_session, conversation, AgentMessageRole.AGENT, "תשובה")

        assert agent_service.messages_left_today(db_session, user) == (
            settings.AGENT_RATE_LIMIT_PER_DAY
        )

    def test_a_message_just_inside_the_window_still_counts(
        self, db_session, user, conversation
    ):
        _say(
            db_session, conversation, AgentMessageRole.USER, "שאלה", minutes_ago=23 * 60
        )

        assert agent_service.messages_left_today(db_session, user) == (
            settings.AGENT_RATE_LIMIT_PER_DAY - 1
        )

    def test_a_message_that_has_aged_out_does_not(self, db_session, user, conversation):
        """The window rolls rather than resetting at midnight — which is what
        stops a user spending two days' budget either side of it."""
        _say(
            db_session, conversation, AgentMessageRole.USER, "שאלה", minutes_ago=25 * 60
        )

        assert agent_service.messages_left_today(db_session, user) == (
            settings.AGENT_RATE_LIMIT_PER_DAY
        )

    def test_another_users_questions_are_not_counted(
        self, db_session, user, conversation, make_user
    ):
        _say(db_session, conversation, AgentMessageRole.USER, "שאלה")
        other = make_user(
            "other@example.com",
            UserType.WIDOW,
            Sector.HASIDIC,
            account_status=AccountStatus.ACTIVE,
        )

        assert agent_service.messages_left_today(db_session, other) == (
            settings.AGENT_RATE_LIMIT_PER_DAY
        )

    def test_the_quota_never_reads_as_negative(
        self, db_session, monkeypatch, user, conversation
    ):
        monkeypatch.setattr(settings, "AGENT_RATE_LIMIT_PER_DAY", 1)
        _say(db_session, conversation, AgentMessageRole.USER, "אחת")
        _say(db_session, conversation, AgentMessageRole.USER, "שתיים")

        assert agent_service.messages_left_today(db_session, user) == 0


# ---------------------------------------------------------------------------
# _recent_turns()
# ---------------------------------------------------------------------------


class TestRecentTurns:
    def test_a_conversation_that_has_not_started_has_no_history(self, db_session):
        assert agent_service._recent_turns(db_session, None) == []

    def test_turns_come_back_oldest_first(self, db_session, conversation):
        _say(db_session, conversation, AgentMessageRole.USER, "ראשונה", minutes_ago=2)
        _say(db_session, conversation, AgentMessageRole.AGENT, "תשובה", minutes_ago=1)

        history = agent_service._recent_turns(db_session, conversation)

        assert [turn.content for turn in history] == ["ראשונה", "תשובה"]
        assert history[0].role == AgentMessageRole.USER

    def test_only_the_newest_turns_survive_the_cap(
        self, db_session, monkeypatch, conversation
    ):
        """A turn is a question and its answer, so N turns is up to 2N rows."""
        monkeypatch.setattr(settings, "AGENT_HISTORY_TURNS", 1)
        _say(db_session, conversation, AgentMessageRole.USER, "ישנה", minutes_ago=4)
        _say(db_session, conversation, AgentMessageRole.AGENT, "ישנה-ת", minutes_ago=3)
        _say(db_session, conversation, AgentMessageRole.USER, "חדשה", minutes_ago=2)
        _say(db_session, conversation, AgentMessageRole.AGENT, "חדשה-ת", minutes_ago=1)

        history = agent_service._recent_turns(db_session, conversation)

        assert [turn.content for turn in history] == ["חדשה", "חדשה-ת"]

    def test_history_can_be_switched_off_entirely(
        self, db_session, monkeypatch, conversation
    ):
        monkeypatch.setattr(settings, "AGENT_HISTORY_TURNS", 0)
        _say(db_session, conversation, AgentMessageRole.USER, "שאלה")

        assert agent_service._recent_turns(db_session, conversation) == []

    def test_the_disclaimer_does_not_go_back_into_the_prompt(
        self, db_session, conversation
    ):
        stored = (
            f"תשובה{agent_service.DISCLAIMER_SEPARATOR}{llm_service.ANSWER_DISCLAIMER}"
        )
        _say(db_session, conversation, AgentMessageRole.AGENT, stored)

        (turn,) = agent_service._recent_turns(db_session, conversation)

        assert turn.content == "תשובה"

    def test_a_disclaimer_quoted_mid_answer_is_left_alone(self):
        """Only the paragraph _compose_answer() appended comes off — matched as
        a suffix, so an answer that happens to mention it keeps its text."""
        quoted = f"{llm_service.ANSWER_DISCLAIMER} — וזה מה שכתוב בהמשך."

        assert agent_service._without_disclaimer(quoted) == quoted


# ---------------------------------------------------------------------------
# _retrieve_for()
# ---------------------------------------------------------------------------


class TestRetrieveFor:
    def test_a_question_that_stands_alone_is_searched_as_written(
        self, db_session, housing_chunk
    ):
        chunks = agent_service._retrieve_for(db_session, DOMAIN, HOUSING_QUESTION, [])

        assert [chunk.title for chunk in chunks] == [HOUSING_TITLE]

    def test_a_follow_up_borrows_the_words_of_the_question_before_it(
        self, db_session, housing_chunk
    ):
        history = [
            llm_service.HistoryTurn(
                role=AgentMessageRole.USER, content=HOUSING_QUESTION
            ),
            llm_service.HistoryTurn(role=AgentMessageRole.AGENT, content="כן, בתנאים."),
        ]

        chunks = agent_service._retrieve_for(
            db_session, DOMAIN, PRONOUN_FOLLOW_UP, history
        )

        assert [chunk.title for chunk in chunks] == [HOUSING_TITLE]

    def test_with_nothing_behind_it_a_bare_follow_up_finds_nothing(
        self, db_session, housing_chunk
    ):
        """The widening is a fallback for a follow-up, not a second attempt for
        every question: an opening message has nothing to widen with."""
        assert (
            agent_service._retrieve_for(db_session, DOMAIN, PRONOUN_FOLLOW_UP, []) == []
        )

    def test_only_the_users_own_words_are_borrowed(self, db_session, housing_chunk):
        """The agent's replies are its words, not a statement of what is being
        asked about — widening with them would search the answer, not the
        question."""
        history = [
            llm_service.HistoryTurn(
                role=AgentMessageRole.AGENT, content=f"לפי {HOUSING_TITLE}, כן."
            )
        ]

        assert (
            agent_service._retrieve_for(db_session, DOMAIN, PRONOUN_FOLLOW_UP, history)
            == []
        )
