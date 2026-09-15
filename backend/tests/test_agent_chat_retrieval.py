"""
The chat flow against the *real* rag_service.retrieve() — PostgreSQL + pgvector.

test_agent_chat.py substitutes a term-overlap FakeRetrieval for the whole of
`rag_service.retrieve()`. That is what keeps its assertions about grounding,
quotas, history and prompt injection runnable on SQLite in about a second, and
it is the right trade for them: what they are about is the chat flow's own
decisions, not retrieval's.

The cost of that substitution is that nothing in it would notice if retrieve()'s
contract moved underneath ABF-122 — a renamed field on RetrievedChunk, a chunk
that stopped carrying its parent entry's source, or a `score` that started
running the other way. Those are exactly the things that changed when ABF-121
landed, and the branch found out by reading the module rather than by a failing
test.

This file closes that gap and nothing else. It fakes **only** the Gemini
embedding call — the same `_fake_vector` stand-in test_rag_service.py uses — and
leaves real: the SQL, pgvector's distance operator, the chunk → RetrievedChunk
mapping, agent_service's relevance floor, and the whole of chat(). It needs the
VECTOR type, so it skips without TEST_POSTGRES_URL and runs on every PR in CI
(ci.yml has run pgvector/pgvector:pg16 since ABF-121).

The model is still a stub. A test that called Gemini would cost money, need a
network, and stop being a test.
"""

import zlib

import pytest

from app.core.config import settings
from app.core.constants import (
    GroupVisibility,
    ProfessionalDomain,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.models.agent import (
    EMBEDDING_DIMENSIONS,
    AgentDomain,
    AgentKnowledgeEntry,
)
from app.models.user import User
from app.schemas.agent import AgentChatRequest
from app.services import agent_service, llm_service, rag_service

HOUSING_TITLE = "סיוע בשכר דירה"
HOUSING_SOURCE_NAME = "אתר משרד השיכון"
HOUSING_SOURCE_URL = "https://example.gov.il/housing"
HOUSING_CHUNK = "אלמנה זכאית להשתתפות בשכר דירה בהתאם להכנסה ולמספר הילדים."
HOUSING_QUESTION = "האם מגיעה לי השתתפות בשכר דירה?"

SCHOOL_TITLE = "הנחות בגני ילדים"
SCHOOL_CHUNK = "הנחה בגני ילדים ניתנת לפי ועדת חריגים של הרשות המקומית."

OFF_TOPIC_QUESTION = "מתי ממריא המטוס לבנגקוק ומה מזג האוויר שם?"


# ---------------------------------------------------------------------------
# The one thing that is faked
# ---------------------------------------------------------------------------


def _fake_vector(text: str) -> list[float]:
    """A deterministic stand-in for a real embedding.

    Copied from test_rag_service.py rather than imported: importing across test
    modules makes one file's refactor break another's, and the eight lines are
    the contract between these two files, not shared machinery.

    Each word lands in one position, so texts sharing words point in similar
    directions. crc32 rather than hash(), which Python salts per process.
    Position 0 carries a constant so an all-unknown text is still non-zero —
    cosine distance to a zero vector is NaN, not a bad score.
    """
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[0] = 0.1
    for word in text.split():
        vector[zlib.crc32(word.encode("utf-8")) % EMBEDDING_DIMENSIONS] += 1.0
    return vector


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    """Replace the Gemini call, keeping everything downstream of it real.

    Autouse: every test in this file goes through retrieval, and one that
    reached the real embedding API would be a test that costs money.
    `embed_text()` delegates to `embed_texts()`, so patching the plural covers
    the query side as well as the indexing side.
    """

    def _embed_texts(texts: list[str], task_type: str) -> list[list[float]]:
        return [_fake_vector(text) for text in texts]

    monkeypatch.setattr(rag_service, "embed_texts", _embed_texts)


# ---------------------------------------------------------------------------
# Everything else is real
# ---------------------------------------------------------------------------


class RecordingProvider:
    """An LLMProvider that answers a fixed string and remembers every call.

    Same role as test_agent_chat.py's: "the answer is grounded" is a claim
    about the *input* the model was handed, so the input has to be kept.
    """

    def __init__(self) -> None:
        self.answer = "לפי המקורות, ייתכן שמגיעה לך השתתפות."
        self.calls: list[dict] = []

    def generate(
        self, system_prompt, user_message, context_chunks, conversation_history
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_message": user_message,
                "context_chunks": list(context_chunks),
                "conversation_history": list(conversation_history),
            }
        )
        return self.answer


@pytest.fixture
def llm(monkeypatch):
    provider = RecordingProvider()
    original = dict(llm_service._PROVIDERS)
    llm_service.register_provider("recording", lambda: provider)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "recording")
    yield provider
    llm_service._PROVIDERS.clear()
    llm_service._PROVIDERS.update(original)


def _add_domain(pg_session, name: str) -> AgentDomain:
    domain = AgentDomain(
        name=name,
        description=name,
        professional_domain=ProfessionalDomain.SOCIAL_WORKER,
        group_visibility=GroupVisibility.ALL,
        sector_visibility=SectorVisibility.ALL,
    )
    pg_session.add(domain)
    pg_session.commit()
    return domain


def _index(pg_session, domain, author, title, content, source_name, source_url):
    entry = AgentKnowledgeEntry(
        domain_id=domain.id,
        title=title,
        content=content,
        source_name=source_name,
        source_url=source_url,
        updated_by=author.id,
    )
    pg_session.add(entry)
    pg_session.commit()
    rag_service.index_entry(pg_session, entry)
    pg_session.commit()
    return entry


@pytest.fixture
def author(pg_session) -> User:
    user = User(
        email="pro@example.com",
        password_hash="hashed",
        first_name="Test",
        last_name="Pro",
        role=UserRole.PROFESSIONAL,
        professional_domain=ProfessionalDomain.SOCIAL_WORKER,
    )
    pg_session.add(user)
    pg_session.commit()
    return user


@pytest.fixture
def asker(pg_session) -> User:
    user = User(
        email="asker@example.com",
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=UserRole.USER,
        user_type=UserType.WIDOW,
        sector=Sector.HASIDIC,
    )
    pg_session.add(user)
    pg_session.commit()
    return user


@pytest.fixture
def housing(pg_session, author) -> AgentDomain:
    """One agent with one indexed entry, on the topic the questions are about."""
    domain = _add_domain(pg_session, "דיור")
    _index(
        pg_session,
        domain,
        author,
        HOUSING_TITLE,
        HOUSING_CHUNK,
        HOUSING_SOURCE_NAME,
        HOUSING_SOURCE_URL,
    )
    return domain


@pytest.fixture
def open_floor(monkeypatch):
    """Let everything retrieval found through to the provider.

    AGENT_MIN_RELEVANCE_SCORE's default of 0.35 is calibrated for real Gemini
    embeddings; `_fake_vector` scores a paraphrase far lower than the real
    model would, because it compares words and not meaning. A test about the
    *contract* that leaned on the default would be asserting the stand-in's
    geometry, and would break the day the default moved for reasons that have
    nothing to do with it.

    -1.0 is the bottom of RetrievedChunk.score's range, so nothing is filtered
    and what reaches the prompt is exactly what retrieve() returned. The tests
    that are about the floor set their own value instead, measured from the
    scores retrieval actually produced.
    """
    monkeypatch.setattr(settings, "AGENT_MIN_RELEVANCE_SCORE", -1.0)


def _ask(pg_session, user, domain, question: str):
    return agent_service.chat(
        pg_session, user, domain.id, AgentChatRequest(message=question)
    )


# ---------------------------------------------------------------------------


class TestTheContractItself:
    """What ABF-122 reads off a RetrievedChunk, read off a real one."""

    def test_the_passage_in_the_prompt_is_the_one_retrieval_really_returned(
        self, pg_session, asker, housing, llm, open_floor
    ) -> None:
        _ask(pg_session, asker, housing, HOUSING_QUESTION)

        assert len(llm.calls) == 1
        chunks = llm.calls[0]["context_chunks"]
        assert [chunk.content for chunk in chunks] == [HOUSING_CHUNK]
        assert chunks[0].title == HOUSING_TITLE

    def test_the_passage_still_carries_its_entrys_provenance(
        self, pg_session, asker, housing, llm, open_floor
    ) -> None:
        """The chunk table stores neither of these — they are joined back from
        the parent entry inside retrieve(). A join that broke would leave the
        answer citing nothing, and nothing else would fail."""
        response = _ask(pg_session, asker, housing, HOUSING_QUESTION)

        chunk = llm.calls[0]["context_chunks"][0]
        assert (chunk.source_name, chunk.source_url) == (
            HOUSING_SOURCE_NAME,
            HOUSING_SOURCE_URL,
        )
        assert [(s.title, s.source_name, s.source_url) for s in response.sources] == [
            (HOUSING_TITLE, HOUSING_SOURCE_NAME, HOUSING_SOURCE_URL)
        ]


class TestTheFloorReadsTheScoreTheRightWayRound:
    """AGENT_MIN_RELEVANCE_SCORE assumes higher-is-better on a real score.

    Not an assertion about 0.35 — the right floor is a property of the
    deployment's content and of GEMINI_EMBED_MODEL, and a fake embedding
    function cannot speak for either. What is asserted is the *direction*: that
    the passage the real retrieve() ranks first is the one the floor keeps, and
    that a floor above everything retrieval found stops the provider being
    called at all.
    """

    def test_a_question_about_the_material_outranks_one_about_nothing(
        self, pg_session, housing
    ) -> None:
        """The premise, measured rather than assumed — and the reason the floor
        has to exist: the off-topic question gets chunks back too."""
        on_topic = rag_service.retrieve(pg_session, housing.id, HOUSING_QUESTION)
        off_topic = rag_service.retrieve(pg_session, housing.id, OFF_TOPIC_QUESTION)

        assert len(off_topic) == 1, "retrieve() ranks; it does not refuse"
        assert on_topic[0].score > off_topic[0].score

    def test_a_floor_between_them_keeps_the_relevant_one_and_drops_the_other(
        self, pg_session, asker, housing, llm, monkeypatch
    ) -> None:
        on_topic = rag_service.retrieve(pg_session, housing.id, HOUSING_QUESTION)
        off_topic = rag_service.retrieve(pg_session, housing.id, OFF_TOPIC_QUESTION)
        between = (on_topic[0].score + off_topic[0].score) / 2
        monkeypatch.setattr(settings, "AGENT_MIN_RELEVANCE_SCORE", between)

        answered = _ask(pg_session, asker, housing, HOUSING_QUESTION)
        refused = _ask(pg_session, asker, housing, OFF_TOPIC_QUESTION)

        assert llm.answer in answered.answer.content
        assert llm_service.NO_CONTEXT_ANSWER in refused.answer.content
        assert len(llm.calls) == 1, "the off-topic question never reached the provider"

    def test_a_floor_above_everything_indexed_refuses_without_calling_anyone(
        self, pg_session, asker, housing, llm, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "AGENT_MIN_RELEVANCE_SCORE", 1.01)

        response = _ask(pg_session, asker, housing, HOUSING_QUESTION)

        assert llm_service.NO_CONTEXT_ANSWER in response.answer.content
        assert llm.calls == []
        assert response.sources == []


class TestDomainScoping:
    def test_another_agents_knowledge_cannot_reach_this_answer(
        self, pg_session, asker, author, housing, llm, open_floor
    ) -> None:
        """Scoping is a WHERE clause inside retrieve(), not something
        agent_service filters afterwards — so it is only ever true here."""
        other = _add_domain(pg_session, "חינוך")
        _index(
            pg_session,
            other,
            author,
            SCHOOL_TITLE,
            SCHOOL_CHUNK,
            "אתר הרשות",
            "https://example.gov.il/education",
        )

        _ask(pg_session, asker, housing, SCHOOL_CHUNK)

        titles = {chunk.title for chunk in llm.calls[0]["context_chunks"]}
        assert SCHOOL_TITLE not in titles
        assert titles == {HOUSING_TITLE}
