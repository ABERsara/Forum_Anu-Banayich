"""
Unit tests for rag_service — chunking, embedding, indexing and retrieval.

Two halves, split by what they need to run:

* Chunking and the Gemini client run everywhere. Neither touches a database,
  and no test here ever calls the real Gemini API — the ticket forbids it, and
  a test that costs money and needs a network is a test that gets skipped.
* Indexing and retrieval need pgvector's VECTOR type and its distance
  operators, which SQLite does not have. They are marked, and skip without
  TEST_POSTGRES_URL. CI sets it, so they run on every PR.

The retrieval tests substitute a fake embedding function rather than a fixed
return value. A stub that answers the same vector every time would let a
`retrieve()` that ignores the query, or sorts backwards, pass. This one maps
words to positions in the vector, so texts that share words really do come out
closer together, and the assertions are about ranking rather than about the
stub.
"""

import zlib

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.constants import AgentMessageRole, ProfessionalDomain, UserRole
from app.models.agent import (
    EMBEDDING_DIMENSIONS,
    AgentConversation,
    AgentDomain,
    AgentKnowledgeChunk,
    AgentKnowledgeEntry,
    AgentMessage,
)
from app.models.user import User
from app.services import rag_service
from app.services.rag_service import (
    TARGET_CHUNK_CHARACTERS,
    TASK_TYPE_DOCUMENT,
    TASK_TYPE_QUERY,
    EmbeddingError,
    chunk_text,
)

# ---------------------------------------------------------------------------
# chunk_text — pure, runs everywhere
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_empty_text_produces_no_chunks(self) -> None:
        assert chunk_text("") == []

    def test_whitespace_only_text_produces_no_chunks(self) -> None:
        # An entry saved with a stray newline in the content field is not an
        # error, it just has nothing to retrieve.
        assert chunk_text("   \n\n  \t ") == []

    def test_short_text_stays_one_chunk(self) -> None:
        text = "אלמנה זכאית להנחה בארנונה."
        assert chunk_text(text) == [text]

    def test_hebrew_content_survives_unchanged(self) -> None:
        # Chunking counts characters, so nothing here re-encodes the text; this
        # pins that a Hebrew entry is stored as it was written.
        text = "הנחה בארנונה למשפחה חד-הורית — עד 100% מהתעריף."
        assert chunk_text(text) == [text]

    def test_short_paragraphs_are_merged_into_one_chunk(self) -> None:
        # Three lines that together are far under the target: splitting them
        # would produce chunks too small to answer anything on their own.
        text = "שורה ראשונה.\n\nשורה שנייה.\n\nשורה שלישית."
        assert len(chunk_text(text)) == 1

    def test_long_text_becomes_several_chunks_in_reading_order(self) -> None:
        paragraphs = [f"פסקה מספר {index}. " * 20 for index in range(4)]
        chunks = chunk_text("\n\n".join(paragraphs))

        assert len(chunks) > 1
        # Order is the order of the source: chunk n+1 starts later in the text
        # than chunk n. Retrieval returns chunks on their own, so a chunk that
        # is out of order is a paragraph quoted out of sequence.
        positions = [chunks[0].find("פסקה מספר 0"), chunks[-1].find("פסקה מספר 3")]
        assert positions[0] >= 0 and positions[1] >= 0

    def test_each_chunk_after_the_first_repeats_the_tail_of_the_one_before(
        self,
    ) -> None:
        paragraphs = [f"פסקה מספר {index}. " * 20 for index in range(4)]
        chunks = chunk_text("\n\n".join(paragraphs))

        for previous, chunk in zip(chunks[:-1], chunks[1:], strict=True):
            overlap = chunk[: rag_service.CHUNK_OVERLAP_CHARACTERS].strip()
            assert overlap and overlap in previous

    def test_a_sentence_longer_than_the_target_is_split_rather_than_kept_whole(
        self,
    ) -> None:
        # No punctuation anywhere: there is no boundary to split on, and the
        # fallback has to cut it rather than emit one enormous chunk.
        chunks = chunk_text("א" * (TARGET_CHUNK_CHARACTERS * 3))

        assert len(chunks) > 1
        assert all(chunk.strip() for chunk in chunks)

    def test_a_paragraph_over_the_target_splits_on_sentence_boundaries(self) -> None:
        sentence = "זוהי פסקה ארוכה מאוד שמכילה משפט שלם. "
        chunks = chunk_text(sentence * 40)

        assert len(chunks) > 1
        # Every chunk ends where a sentence ends, not mid-word.
        assert all(chunk.rstrip().endswith(".") for chunk in chunks)


# ---------------------------------------------------------------------------
# embed_texts — the Gemini client, mocked. Runs everywhere.
# ---------------------------------------------------------------------------


def _embedding_response(count: int) -> httpx.Response:
    """A batchEmbedContents response carrying `count` well-formed vectors."""
    return httpx.Response(
        200,
        json={
            "embeddings": [
                {"values": [0.01] * EMBEDDING_DIMENSIONS} for _ in range(count)
            ]
        },
        request=httpx.Request("POST", "https://example.invalid"),
    )


@pytest.fixture
def gemini_key(monkeypatch):
    monkeypatch.setattr(rag_service.settings, "GEMINI_API_KEY", "test-key")


@pytest.fixture
def captured_request(monkeypatch, gemini_key):
    """Capture the outgoing call instead of making it."""
    captured: dict[str, object] = {}

    def _post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured.update(kwargs)
        requests = kwargs["json"]["requests"]  # type: ignore[index,call-overload]
        return _embedding_response(len(requests))

    monkeypatch.setattr(rag_service.httpx, "post", _post)
    return captured


class TestEmbedText:
    def test_returns_a_vector_of_the_stored_width(self, captured_request) -> None:
        # Anything else cannot be written to the vector(768) column at all.
        vector = rag_service.embed_text("שאלה", TASK_TYPE_QUERY)
        assert len(vector) == EMBEDDING_DIMENSIONS

    def test_sends_the_configured_model_and_the_task_type(
        self, captured_request, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            rag_service.settings, "GEMINI_EMBED_MODEL", "text-embedding-004"
        )
        rag_service.embed_text("שאלה", TASK_TYPE_QUERY)

        assert "models/text-embedding-004" in captured_request["url"]
        request = captured_request["json"]["requests"][0]
        assert request["taskType"] == TASK_TYPE_QUERY
        assert request["model"] == "models/text-embedding-004"

    def test_indexing_and_querying_use_different_task_types(
        self, captured_request
    ) -> None:
        # The pairing Gemini is trained on. Indexing under the query task type
        # is a mistake that only shows up as mediocre answers months later.
        rag_service.embed_texts(["מסמך"], TASK_TYPE_DOCUMENT)
        assert captured_request["json"]["requests"][0]["taskType"] == TASK_TYPE_DOCUMENT

        rag_service.embed_text("שאלה", TASK_TYPE_QUERY)
        assert captured_request["json"]["requests"][0]["taskType"] == TASK_TYPE_QUERY

    def test_the_api_key_travels_in_a_header_not_the_url(
        self, captured_request
    ) -> None:
        # A key in the query string is a key in every access log it passes.
        rag_service.embed_text("שאלה", TASK_TYPE_QUERY)

        assert captured_request["headers"]["x-goog-api-key"] == "test-key"
        assert "test-key" not in captured_request["url"]

    def test_all_chunks_go_out_in_one_request(self, captured_request) -> None:
        rag_service.embed_texts(["א", "ב", "ג"], TASK_TYPE_DOCUMENT)
        assert len(captured_request["json"]["requests"]) == 3

    def test_the_configured_timeout_is_applied(
        self, captured_request, monkeypatch
    ) -> None:
        monkeypatch.setattr(rag_service.settings, "GEMINI_TIMEOUT_SECONDS", 3)
        rag_service.embed_text("שאלה", TASK_TYPE_QUERY)
        assert captured_request["timeout"] == 3

    def test_embedding_nothing_makes_no_request(self, captured_request) -> None:
        # An entry whose content chunks to nothing must not cost a round trip.
        assert rag_service.embed_texts([], TASK_TYPE_DOCUMENT) == []
        assert captured_request == {}


class TestEmbedTextFailures:
    def test_a_missing_api_key_says_so(self, monkeypatch) -> None:
        # Named at the boundary rather than surfacing as a 401 from Google.
        monkeypatch.setattr(rag_service.settings, "GEMINI_API_KEY", "")

        with pytest.raises(EmbeddingError, match="GEMINI_API_KEY"):
            rag_service.embed_text("שאלה", TASK_TYPE_QUERY)

    def test_a_missing_api_key_is_caught_before_any_request(self, monkeypatch) -> None:
        monkeypatch.setattr(rag_service.settings, "GEMINI_API_KEY", "")

        def _fail(*args: object, **kwargs: object) -> httpx.Response:
            raise AssertionError("no request should be made without a key")

        monkeypatch.setattr(rag_service.httpx, "post", _fail)

        with pytest.raises(EmbeddingError):
            rag_service.embed_text("שאלה", TASK_TYPE_QUERY)

    def test_an_http_error_becomes_an_embedding_error(
        self, monkeypatch, gemini_key
    ) -> None:
        def _post(url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(
                429,
                json={"error": {"message": "quota exceeded for שאלה"}},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(rag_service.httpx, "post", _post)

        with pytest.raises(EmbeddingError) as raised:
            rag_service.embed_text("שאלה", TASK_TYPE_QUERY)
        assert "429" in str(raised.value)

    def test_an_http_error_does_not_quote_the_content_back(
        self, monkeypatch, gemini_key
    ) -> None:
        # A rejected call echoes the text it was sent. That text is knowledge
        # base content, and this message goes to the logs.
        def _post(url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(
                400,
                json={"error": {"message": "bad input: סוד רפואי"}},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(rag_service.httpx, "post", _post)

        with pytest.raises(EmbeddingError) as raised:
            rag_service.embed_text("סוד רפואי", TASK_TYPE_QUERY)
        assert "סוד רפואי" not in str(raised.value)

    def test_a_timeout_becomes_an_embedding_error(
        self, monkeypatch, gemini_key
    ) -> None:
        def _post(url: str, **kwargs: object) -> httpx.Response:
            raise httpx.ReadTimeout("too slow")

        monkeypatch.setattr(rag_service.httpx, "post", _post)

        with pytest.raises(EmbeddingError, match="timed out"):
            rag_service.embed_text("שאלה", TASK_TYPE_QUERY)

    def test_a_short_batch_is_refused_rather_than_misaligned(
        self, monkeypatch, gemini_key
    ) -> None:
        # Storing three chunks against two vectors would silently attach the
        # wrong meaning to the third — worse than failing.
        def _post(url: str, **kwargs: object) -> httpx.Response:
            return _embedding_response(2)

        monkeypatch.setattr(rag_service.httpx, "post", _post)

        with pytest.raises(EmbeddingError, match="2 embeddings for 3"):
            rag_service.embed_texts(["א", "ב", "ג"], TASK_TYPE_DOCUMENT)


# ---------------------------------------------------------------------------
# index_entry / retrieve — PostgreSQL + pgvector only
# ---------------------------------------------------------------------------


def _fake_vector(text: str) -> list[float]:
    """A deterministic stand-in for a real embedding.

    Each word lands in one position of the vector, so two texts that share
    words point in similar directions and two that share none do not. crc32
    rather than hash(): Python salts string hashing per process, which would
    make these tests pass or fail depending on the run.

    Position 0 carries a small constant so that a text of unknown words is
    still a non-zero vector — cosine distance to a zero vector is undefined,
    and would come back as NaN instead of a bad score.
    """
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[0] = 0.1
    for word in text.split():
        vector[zlib.crc32(word.encode("utf-8")) % EMBEDDING_DIMENSIONS] += 1.0
    return vector


@pytest.fixture
def fake_embeddings(monkeypatch):
    """Replace the Gemini call, keeping everything downstream of it real."""

    def _embed_texts(texts: list[str], task_type: str) -> list[list[float]]:
        return [_fake_vector(text) for text in texts]

    monkeypatch.setattr(rag_service, "embed_texts", _embed_texts)


@pytest.fixture
def domain(pg_session) -> AgentDomain:
    from app.core.constants import GroupVisibility, SectorVisibility

    domain = AgentDomain(
        name="זכויות",
        description="זכויות ותשלומים",
        professional_domain=ProfessionalDomain.LAWYER,
        group_visibility=GroupVisibility.ALL,
        sector_visibility=SectorVisibility.ALL,
    )
    pg_session.add(domain)
    pg_session.commit()
    return domain


@pytest.fixture
def author(pg_session) -> User:
    user = User(
        email="pro@example.com",
        password_hash="hashed",
        first_name="Test",
        last_name="Pro",
        role=UserRole.PROFESSIONAL,
        professional_domain=ProfessionalDomain.LAWYER,
    )
    pg_session.add(user)
    pg_session.commit()
    return user


def _add_entry(
    pg_session,
    domain: AgentDomain,
    author: User,
    title: str,
    content: str,
) -> AgentKnowledgeEntry:
    entry = AgentKnowledgeEntry(
        domain_id=domain.id,
        title=title,
        content=content,
        source_name="אתר הרשות",
        source_url="https://example.gov.il/arnona",
        updated_by=author.id,
    )
    pg_session.add(entry)
    pg_session.commit()
    return entry


def _chunks_of(pg_session, entry: AgentKnowledgeEntry) -> list[AgentKnowledgeChunk]:
    return (
        pg_session.query(AgentKnowledgeChunk)
        .filter(AgentKnowledgeChunk.entry_id == entry.id)
        .order_by(AgentKnowledgeChunk.chunk_index)
        .all()
    )


class TestIndexEntry:
    def test_indexing_stores_one_chunk_per_slice_numbered_from_zero(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        content = "\n\n".join(f"פסקה מספר {index}. " * 20 for index in range(4))
        entry = _add_entry(pg_session, domain, author, "ארנונה", content)

        rag_service.index_entry(pg_session, entry)

        chunks = _chunks_of(pg_session, entry)
        assert len(chunks) == len(rag_service.chunk_text(content))
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
        assert all(len(c.embedding) == EMBEDDING_DIMENSIONS for c in chunks)

    def test_re_indexing_replaces_the_old_chunks_rather_than_adding_to_them(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        # The failure this guards: an edit that leaves the previous version's
        # chunks in the table, so the agent answers from text nobody can see.
        entry = _add_entry(
            pg_session, domain, author, "ארנונה", "התוכן המקורי על ארנונה."
        )
        rag_service.index_entry(pg_session, entry)

        entry.content = "התוכן המעודכן על מים."
        pg_session.commit()
        rag_service.index_entry(pg_session, entry)

        chunks = _chunks_of(pg_session, entry)
        assert [c.chunk_text for c in chunks] == ["התוכן המעודכן על מים."]

    def test_re_indexing_the_same_content_twice_is_not_blocked_by_the_constraint(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        # UNIQUE(entry_id, chunk_index) would reject the second run outright if
        # the rebuild did not delete before inserting.
        entry = _add_entry(pg_session, domain, author, "ארנונה", "תוכן.")

        rag_service.index_entry(pg_session, entry)
        rag_service.index_entry(pg_session, entry)

        assert len(_chunks_of(pg_session, entry)) == 1

    def test_an_entry_with_no_indexable_content_stores_no_chunks(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        entry = _add_entry(pg_session, domain, author, "ריק", "   ")

        rag_service.index_entry(pg_session, entry)

        assert _chunks_of(pg_session, entry) == []

    def test_deleting_an_entry_takes_its_chunks_with_it(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        entry = _add_entry(pg_session, domain, author, "ארנונה", "תוכן על ארנונה.")
        rag_service.index_entry(pg_session, entry)
        assert _chunks_of(pg_session, entry)

        pg_session.delete(entry)
        pg_session.commit()

        assert pg_session.query(AgentKnowledgeChunk).count() == 0

    def test_deleting_a_domain_takes_its_entries_and_their_chunks(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        # The inherited gap this migration closes: before the FK carried
        # ON DELETE CASCADE, this raised rather than cascading.
        entry = _add_entry(pg_session, domain, author, "ארנונה", "תוכן על ארנונה.")
        rag_service.index_entry(pg_session, entry)

        pg_session.execute(
            AgentDomain.__table__.delete().where(AgentDomain.id == domain.id)
        )
        pg_session.commit()

        assert pg_session.query(AgentKnowledgeEntry).count() == 0
        assert pg_session.query(AgentKnowledgeChunk).count() == 0

    def test_a_domain_that_has_been_talked_to_cannot_be_deleted(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        """The knowledge side cascades; the conversation side deliberately does not.

        agent_conversations.domain_id carries no ON DELETE rule, so a domain
        somebody has used is not deletable at all. That is the intended
        behaviour, and was decided deliberately: agent_messages.content
        holds what a bereaved member wrote to the agent, and a catalog edit must
        not be able to erase it as a side effect. Retiring a domain is what
        AgentDomain.is_active is for.

        Pinned here so the next person to reach for ON DELETE CASCADE finds a
        failing test and this paragraph, rather than an FK that merely looks
        like an oversight.
        """
        entry = _add_entry(pg_session, domain, author, "ארנונה", "תוכן על ארנונה.")
        rag_service.index_entry(pg_session, entry)
        conversation = AgentConversation(user_id=author.id, domain_id=domain.id)
        pg_session.add(conversation)
        pg_session.commit()
        pg_session.add(
            AgentMessage(
                conversation_id=conversation.id,
                role=AgentMessageRole.USER,
                content="<encrypted>",
            )
        )
        pg_session.commit()

        with pytest.raises(IntegrityError):
            pg_session.execute(
                AgentDomain.__table__.delete().where(AgentDomain.id == domain.id)
            )
            pg_session.commit()
        pg_session.rollback()

        # The whole statement rolls back, so the knowledge base survives too —
        # a half-deleted domain is not a state this can leave behind.
        assert pg_session.query(AgentDomain).count() == 1
        assert pg_session.query(AgentKnowledgeEntry).count() == 1
        assert pg_session.query(AgentKnowledgeChunk).count() == 1
        assert pg_session.query(AgentMessage).count() == 1


class TestRetrieve:
    def test_a_question_finds_the_entry_that_answers_it(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        """The ticket's own acceptance example, end to end."""
        wanted = _add_entry(
            pg_session,
            domain,
            author,
            "הנחה בארנונה למשפחה חד-הורית",
            "משפחה חד-הורית זכאית להנחה בארנונה בשיעור של עד 100 אחוז.",
        )
        _add_entry(
            pg_session,
            domain,
            author,
            "חיסונים לילדים",
            "לוח חיסונים לילדים בגיל הרך בטיפת חלב.",
        )
        for entry in pg_session.query(AgentKnowledgeEntry).all():
            rag_service.index_entry(pg_session, entry)

        results = rag_service.retrieve(
            pg_session, domain.id, "האם מגיע לי הנחה בארנונה", k=1
        )

        assert [result.title for result in results] == [wanted.title]

    def test_results_carry_the_chunk_text_and_the_parent_entry_source(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        # content is the passage; title and source come from the entry, so an
        # answer built on this can cite where it came from.
        entry = _add_entry(
            pg_session, domain, author, "ארנונה", "הנחה בארנונה למשפחה חד-הורית."
        )
        rag_service.index_entry(pg_session, entry)

        result = rag_service.retrieve(pg_session, domain.id, "הנחה בארנונה")[0]

        assert result.content == "הנחה בארנונה למשפחה חד-הורית."
        assert result.title == "ארנונה"
        assert result.source_name == "אתר הרשות"
        assert result.source_url == "https://example.gov.il/arnona"

    def test_results_come_back_best_first(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        for title, content in (
            ("ארנונה", "הנחה בארנונה למשפחה חד-הורית."),
            ("חיסונים", "לוח חיסונים לילדים."),
            ("מים", "הנחה בתעריף מים."),
        ):
            entry = _add_entry(pg_session, domain, author, title, content)
            rag_service.index_entry(pg_session, entry)

        results = rag_service.retrieve(pg_session, domain.id, "הנחה בארנונה")

        scores = [result.score for result in results]
        assert scores == sorted(scores, reverse=True)

    def test_k_limits_how_many_come_back(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        for index in range(5):
            entry = _add_entry(
                pg_session, domain, author, f"נושא {index}", f"תוכן מספר {index}."
            )
            rag_service.index_entry(pg_session, entry)

        assert len(rag_service.retrieve(pg_session, domain.id, "תוכן", k=2)) == 2

    def test_an_empty_domain_returns_nothing_rather_than_failing(
        self, pg_session, domain, fake_embeddings
    ) -> None:
        # A knowledge base still being filled in is a normal state.
        assert rag_service.retrieve(pg_session, domain.id, "שאלה כלשהי") == []

    def test_chunks_of_another_domain_are_never_returned(
        self, pg_session, domain, author, fake_embeddings
    ) -> None:
        from app.core.constants import GroupVisibility, SectorVisibility

        other = AgentDomain(
            name="בריאות",
            description="בריאות",
            professional_domain=ProfessionalDomain.MEDICINE,
            group_visibility=GroupVisibility.ALL,
            sector_visibility=SectorVisibility.ALL,
        )
        pg_session.add(other)
        pg_session.commit()

        entry = AgentKnowledgeEntry(
            domain_id=other.id,
            title="הנחה בארנונה",
            content="הנחה בארנונה למשפחה חד-הורית.",
            updated_by=author.id,
        )
        pg_session.add(entry)
        pg_session.commit()
        rag_service.index_entry(pg_session, entry)

        # The same words the other domain's entry is made of.
        assert rag_service.retrieve(pg_session, domain.id, "הנחה בארנונה") == []

    def test_a_blank_query_costs_no_embedding_call(self, pg_session, domain) -> None:
        # No fake_embeddings fixture here on purpose: if this reached the Gemini
        # client it would raise on the missing key instead of returning [].
        assert rag_service.retrieve(pg_session, domain.id, "   ") == []


class TestEmbedBatching:
    """A long entry chunks past what one batchEmbedContents call accepts."""

    @pytest.fixture
    def captured_batches(self, monkeypatch, gemini_key):
        batches: list[int] = []

        def _post(url: str, **kwargs: object) -> httpx.Response:
            requests = kwargs["json"]["requests"]  # type: ignore[index,call-overload]
            batches.append(len(requests))
            return _embedding_response(len(requests))

        monkeypatch.setattr(rag_service.httpx, "post", _post)
        return batches

    def test_a_batch_at_the_limit_is_one_request(self, captured_batches) -> None:
        rag_service.embed_texts(
            ["x"] * rag_service.MAX_TEXTS_PER_BATCH, TASK_TYPE_DOCUMENT
        )
        assert captured_batches == [rag_service.MAX_TEXTS_PER_BATCH]

    def test_more_than_the_limit_is_split_rather_than_rejected(
        self, captured_batches
    ) -> None:
        # The failure this prevents: Gemini rejects the whole call, the endpoint
        # swallows it, and an entry stays permanently unindexable because its
        # size is what breaks it — every retry fails the same way.
        count = rag_service.MAX_TEXTS_PER_BATCH + 5
        vectors = rag_service.embed_texts(["x"] * count, TASK_TYPE_DOCUMENT)

        assert captured_batches == [rag_service.MAX_TEXTS_PER_BATCH, 5]
        assert len(vectors) == count

    def test_every_batch_is_embedded_under_the_same_task_type(
        self, captured_batches, monkeypatch
    ) -> None:
        seen: list[str] = []

        def _post(url: str, **kwargs: object) -> httpx.Response:
            requests = kwargs["json"]["requests"]  # type: ignore[index,call-overload]
            seen.extend(request["taskType"] for request in requests)
            return _embedding_response(len(requests))

        monkeypatch.setattr(rag_service.httpx, "post", _post)
        rag_service.embed_texts(
            ["x"] * (rag_service.MAX_TEXTS_PER_BATCH + 1), TASK_TYPE_DOCUMENT
        )

        assert set(seen) == {TASK_TYPE_DOCUMENT}


class TestMalformedGeminiResponses:
    """Everything reaching the endpoint has to arrive as EmbeddingError.

    That is the only exception it treats as "saved but not indexed". Anything
    else becomes a 500 on a write that already succeeded.
    """

    def test_a_body_that_is_not_json_becomes_an_embedding_error(
        self, monkeypatch, gemini_key
    ) -> None:
        # A proxy or captive portal answering 200 with an HTML error page.
        def _post(url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(
                200,
                text="<html>gateway</html>",
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(rag_service.httpx, "post", _post)

        with pytest.raises(EmbeddingError, match="not JSON"):
            rag_service.embed_text("שאלה", TASK_TYPE_QUERY)

    def test_a_body_without_embeddings_becomes_an_embedding_error(
        self, monkeypatch, gemini_key
    ) -> None:
        def _post(url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(
                200, json={"error": "nope"}, request=httpx.Request("POST", url)
            )

        monkeypatch.setattr(rag_service.httpx, "post", _post)

        with pytest.raises(EmbeddingError, match="expected embeddings"):
            rag_service.embed_text("שאלה", TASK_TYPE_QUERY)

    def test_an_embedding_without_values_becomes_an_embedding_error(
        self, monkeypatch, gemini_key
    ) -> None:
        def _post(url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(
                200,
                json={"embeddings": [{"statistics": {}}]},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(rag_service.httpx, "post", _post)

        with pytest.raises(EmbeddingError, match="expected embeddings"):
            rag_service.embed_text("שאלה", TASK_TYPE_QUERY)


class TestAFailedReIndex:
    """PostgreSQL-only: what survives in the table when embedding fails."""

    def test_a_failed_re_index_leaves_no_stale_chunks_behind(
        self, pg_session, domain, author, fake_embeddings, monkeypatch
    ) -> None:
        """The case this is really about is a correction.

        A professional publishes something wrong, edits it to fix it, and is
        told it saved. If the old chunks were still there because embedding the
        new text failed, the agent would go on quoting the statement she just
        retracted — and nothing on her screen would say so.
        """
        entry = _add_entry(
            pg_session, domain, author, "ארנונה", "מגיעה הנחה של 100 אחוז."
        )
        rag_service.index_entry(pg_session, entry)
        assert _chunks_of(pg_session, entry)

        entry.content = "לא מגיעה הנחה כלל."
        pg_session.commit()

        def _fail(texts: list[str], task_type: str) -> list[list[float]]:
            raise rag_service.EmbeddingError("Gemini is unreachable")

        monkeypatch.setattr(rag_service, "embed_texts", _fail)

        with pytest.raises(rag_service.EmbeddingError):
            rag_service.index_entry(pg_session, entry)

        assert _chunks_of(pg_session, entry) == []

    def test_the_entry_itself_survives_a_failed_re_index(
        self, pg_session, domain, author, fake_embeddings, monkeypatch
    ) -> None:
        # Only the derived chunks go. The professional's text is not collateral.
        entry = _add_entry(pg_session, domain, author, "ארנונה", "תוכן.")

        def _fail(texts: list[str], task_type: str) -> list[list[float]]:
            raise rag_service.EmbeddingError("Gemini is unreachable")

        monkeypatch.setattr(rag_service, "embed_texts", _fail)
        with pytest.raises(rag_service.EmbeddingError):
            rag_service.index_entry(pg_session, entry)

        pg_session.rollback()
        assert pg_session.get(AgentKnowledgeEntry, entry.id) is not None

    def test_a_later_successful_run_indexes_the_current_text(
        self, pg_session, domain, author, fake_embeddings, monkeypatch
    ) -> None:
        entry = _add_entry(pg_session, domain, author, "ארנונה", "התוכן הנוכחי.")

        def _fail(texts: list[str], task_type: str) -> list[list[float]]:
            raise rag_service.EmbeddingError("Gemini is unreachable")

        monkeypatch.setattr(rag_service, "embed_texts", _fail)
        with pytest.raises(rag_service.EmbeddingError):
            rag_service.index_entry(pg_session, entry)
        pg_session.rollback()

        monkeypatch.setattr(
            rag_service,
            "embed_texts",
            lambda texts, task_type: [_fake_vector(text) for text in texts],
        )
        rag_service.index_entry(pg_session, entry)

        assert [c.chunk_text for c in _chunks_of(pg_session, entry)] == [
            "התוכן הנוכחי."
        ]


class TestTheTitleReachesTheEmbedding:
    """PostgreSQL-only: the title is embedded with each chunk, not stored in it."""

    @pytest.fixture
    def embedded_texts(self, monkeypatch):
        """Every text handed to the embedder, in order."""
        seen: list[str] = []

        def _embed_texts(texts: list[str], task_type: str) -> list[list[float]]:
            seen.extend(texts)
            return [_fake_vector(text) for text in texts]

        monkeypatch.setattr(rag_service, "embed_texts", _embed_texts)
        return seen

    def test_each_chunk_is_embedded_with_the_title_in_front_of_it(
        self, pg_session, domain, author, embedded_texts
    ) -> None:
        content = "\n\n".join(f"פסקה מספר {index}. " * 20 for index in range(3))
        entry = _add_entry(pg_session, domain, author, "ארנונה", content)

        rag_service.index_entry(pg_session, entry)

        assert embedded_texts
        assert all(text.startswith("ארנונה\n\n") for text in embedded_texts)

    def test_the_stored_chunk_does_not_carry_the_title(
        self, pg_session, domain, author, embedded_texts
    ) -> None:
        # What comes back is quoted to a member as the source's own words, so
        # it must not have a heading glued onto it that the author never wrote
        # in that paragraph.
        entry = _add_entry(
            pg_session, domain, author, "ארנונה", "הזכאות ניתנת עד 100 אחוז."
        )

        rag_service.index_entry(pg_session, entry)

        assert [c.chunk_text for c in _chunks_of(pg_session, entry)] == [
            "הזכאות ניתנת עד 100 אחוז."
        ]

    def test_a_paragraph_that_leans_on_its_heading_is_still_found_by_it(
        self, pg_session, domain, author, embedded_texts
    ) -> None:
        """The case that justified embedding the title at all.

        Neither paragraph repeats the subject its heading names — both are built
        from the same generic phrases. Without the title in the vector the two
        are indistinguishable, and the wrong one can win.
        """
        wanted = _add_entry(
            pg_session,
            domain,
            author,
            "הנחה בארנונה למשפחה חד-הורית",
            "הזכאות ניתנת עד גובה 100 אחוז מהתעריף, ומחייבת הצגת תעודת זהות ותצהיר.",
        )
        _add_entry(
            pg_session,
            domain,
            author,
            "חיסונים לילדים",
            "הזכאות ניתנת עד גיל שנתיים, ומחייבת הצגת תעודת זהות בטיפת חלב.",
        )
        for entry in pg_session.query(AgentKnowledgeEntry).all():
            rag_service.index_entry(pg_session, entry)

        results = rag_service.retrieve(
            pg_session, domain.id, "האם מגיע לי הנחה בארנונה", k=2
        )

        assert results[0].title == wanted.title
        # A clear margin, not a coin flip between two near-identical scores.
        assert results[0].score > results[1].score

    def test_renaming_an_entry_re_embeds_it_under_the_new_title(
        self, pg_session, domain, author, embedded_texts
    ) -> None:
        # The obligation that embedding the title creates, and that the PATCH
        # endpoint honours by re-indexing on a title change.
        entry = _add_entry(pg_session, domain, author, "ארנונה", "הזכאות ניתנת.")
        rag_service.index_entry(pg_session, entry)

        entry.title = "מים"
        pg_session.commit()
        embedded_texts.clear()
        rag_service.index_entry(pg_session, entry)

        assert all(text.startswith("מים\n\n") for text in embedded_texts)
