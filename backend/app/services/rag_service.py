"""
Retrieval-augmented generation over an agent domain's knowledge base.

The problem this solves
-----------------------
A domain's knowledge base grows to more text than any prompt can hold, and most
of it has nothing to do with the question being asked. So the content is sliced
into chunks once, at write time, and each chunk is stored next to an embedding —
a vector that places it by meaning rather than by the words it happens to use.
A question is embedded the same way, and the chunks nearest to it come back.
"האם מגיע לי הנחה בארנונה" finds a paragraph about "הנחה בארנונה למשפחה
חד-הורית" without the two sharing a full phrase.

Chunks are cut from an entry's content, and embedded with its title in front of
them so a paragraph that leans on its heading for the subject can still be found
by it — see index_entry().

Three pieces, deliberately separable:

* `chunk_text()` – pure, no I/O, no DB. Every chunking rule is testable without
  a network or a database.
* `embed_text()` / `embed_texts()` – the only code here that talks to Gemini.
* `index_entry()` / `retrieve()` – the write and read sides that use both.

`retrieve()` returns `RetrievedChunk`, a plain dataclass rather than ORM rows,
so the chat side that consumes it depends on five named fields instead of on
this table's schema, and needs no live session to read them.

Indexing is an explicit call, never an ORM event
------------------------------------------------
`index_entry()` is called from the endpoint *after* the entry is committed. An
event hook would put a multi-second HTTP call inside the transaction that is
writing the entry, holding its locks open on a third party's latency — the same
reason auth_service.register() and report_service send their email after the
commit rather than during it. The same rule is kept inside `index_entry()`
itself, which is why it commits twice around the embedding call rather than
wrapping one transaction over it.
"""

import logging
import re
from dataclasses import dataclass

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import (
    EMBEDDING_DIMENSIONS,
    AgentKnowledgeChunk,
    AgentKnowledgeEntry,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

# Characters, not tokens. A tokenizer would be more precise for English and
# would need a model-specific vocabulary to be right about Hebrew at all;
# counting characters is honest in both and needs no dependency. 600 is roughly
# a long paragraph: big enough to keep a rule and its condition together, small
# enough that a retrieved chunk is mostly answer rather than surrounding text.
TARGET_CHUNK_CHARACTERS = 600

# ~10% carried over from the end of the previous chunk, so a sentence split
# across a boundary is still whole in one of them. Without it, the one paragraph
# that answers the question can end up as two halves that each match it weakly.
CHUNK_OVERLAP_CHARACTERS = 60

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")

# Sentence end: . ! ? the Hebrew sof pasuq (׃) or an ellipsis, followed by
# whitespace. Kept simple on purpose — a wrong split costs a slightly awkward
# chunk boundary, not a wrong answer.
_SENTENCE_END = re.compile(r"(?<=[.!?׃…])\s+")


def chunk_text(text: str) -> list[str]:
    """Split `text` into overlapping chunks of roughly TARGET_CHUNK_CHARACTERS.

    Paragraph boundaries are respected first, because a paragraph is already the
    author's own unit of one idea. Short paragraphs are merged up to the target
    so a chunk carries enough context to stand alone; a paragraph longer than
    the target is split on sentence boundaries, and a single sentence longer
    than the target (a list written without punctuation, say) is cut at the
    target rather than left to dominate a chunk on its own.

    Empty or whitespace-only text yields no chunks at all — an entry can be
    saved with nothing indexable in it, and that is not an error.
    """
    pieces: list[str] = []
    for raw_paragraph in _PARAGRAPH_BREAK.split(text):
        paragraph = raw_paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= TARGET_CHUNK_CHARACTERS:
            pieces.append(paragraph)
        else:
            pieces.extend(_split_long_paragraph(paragraph))

    return _with_overlap(_merge_short(pieces))


def _split_long_paragraph(paragraph: str) -> list[str]:
    """Break one over-long paragraph on sentence boundaries."""
    chunks: list[str] = []
    current = ""
    for raw_sentence in _SENTENCE_END.split(paragraph):
        sentence = raw_sentence.strip()
        if not sentence:
            continue
        if len(sentence) > TARGET_CHUNK_CHARACTERS:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(sentence))
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > TARGET_CHUNK_CHARACTERS:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _hard_split(sentence: str) -> list[str]:
    """Last resort for a sentence with no usable boundary inside it."""
    return [
        sentence[start : start + TARGET_CHUNK_CHARACTERS]
        for start in range(0, len(sentence), TARGET_CHUNK_CHARACTERS)
    ]


def _merge_short(pieces: list[str]) -> list[str]:
    """Join consecutive pieces while they still fit inside one chunk."""
    merged: list[str] = []
    for piece in pieces:
        if merged and len(merged[-1]) + 2 + len(piece) <= TARGET_CHUNK_CHARACTERS:
            merged[-1] = f"{merged[-1]}\n\n{piece}"
        else:
            merged.append(piece)
    return merged


def _with_overlap(chunks: list[str]) -> list[str]:
    """Prefix each chunk after the first with the tail of the one before it.

    The tail is snapped forward to a word boundary when one is near its start,
    so the overlap does not open with half a word.
    """
    if len(chunks) < 2:
        return chunks

    overlapped = [chunks[0]]
    for previous, chunk in zip(chunks[:-1], chunks[1:], strict=True):
        tail = previous[-CHUNK_OVERLAP_CHARACTERS:]
        space = tail.find(" ")
        if 0 <= space < CHUNK_OVERLAP_CHARACTERS // 2:
            tail = tail[space + 1 :]
        overlapped.append(f"{tail.strip()} {chunk}".strip())
    return overlapped


# ---------------------------------------------------------------------------
# Embeddings (Gemini)
# ---------------------------------------------------------------------------

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Which side of the pair a text is on. Gemini embeds a document and the question
# that should find it into deliberately different shapes, and a corpus indexed
# under the wrong one can only be corrected by re-embedding all of it — which is
# why this is here from the first row written, rather than added once retrieval
# starts disappointing someone.
TASK_TYPE_DOCUMENT = "RETRIEVAL_DOCUMENT"
TASK_TYPE_QUERY = "RETRIEVAL_QUERY"

# Gemini rejects a batchEmbedContents call carrying more than 100 requests. A
# long entry chunks past that, so embed_texts() splits rather than letting the
# whole call fail on a threshold nobody writing content can see.
MAX_TEXTS_PER_BATCH = 100


class EmbeddingError(RuntimeError):
    """An embedding could not be produced.

    Never reaches the client as-is: a failed indexing run leaves the entry saved
    and simply not yet retrievable, which the endpoint logs rather than reports.
    """


def embed_text(text: str, task_type: str) -> list[float]:
    """Embed a single text — the query side of retrieval."""
    return embed_texts([text], task_type)[0]


def embed_texts(texts: list[str], task_type: str) -> list[list[float]]:
    """Embed several texts, in as few requests as Gemini allows.

    Indexing an entry means embedding all of its chunks, and the batch endpoint
    takes them together: one round trip instead of one per chunk. It caps a
    batch at MAX_TEXTS_PER_BATCH, so a long entry goes out as several — sending
    them all at once would have the whole call rejected, and a rejection that
    depends on how much a professional wrote is one that would keep happening
    on every retry.
    """
    if not texts:
        return []
    if not settings.GEMINI_API_KEY:
        raise EmbeddingError(
            "GEMINI_API_KEY is not set, so knowledge base content cannot be "
            "embedded. Set it in the environment to enable indexing."
        )

    embeddings: list[list[float]] = []
    for start in range(0, len(texts), MAX_TEXTS_PER_BATCH):
        embeddings.extend(
            _embed_one_batch(texts[start : start + MAX_TEXTS_PER_BATCH], task_type)
        )
    return embeddings


def _embed_one_batch(texts: list[str], task_type: str) -> list[list[float]]:
    """One batchEmbedContents call, with every failure named as an EmbeddingError.

    Everything that can go wrong here has to arrive as EmbeddingError, because
    that is the single exception the endpoint knows to treat as "saved but not
    indexed". A KeyError escaping from a response of an unexpected shape would
    reach the client as a 500 on a write that actually succeeded.
    """
    model = f"models/{settings.GEMINI_EMBED_MODEL}"
    payload = {
        "requests": [
            {
                "model": model,
                "content": {"parts": [{"text": text}]},
                "taskType": task_type,
                # Asked for explicitly, never left to the model's default.
                # gemini-embedding-001 returns 3072 unless told otherwise, and
                # the column is vector(768): the mismatch would not surface
                # here but as a failed INSERT two steps later, which _index()
                # swallows — leaving an entry that saves and is never
                # retrievable, with a log line as the only symptom.
                "outputDimensionality": EMBEDDING_DIMENSIONS,
            }
            for text in texts
        ]
    }

    try:
        response = httpx.post(
            f"{GEMINI_API_BASE}/{model}:batchEmbedContents",
            json=payload,
            # In a header rather than the ?key= query parameter: URLs end up in
            # access logs and error traces, and this one is a live secret.
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            timeout=settings.GEMINI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
    except httpx.TimeoutException as exc:
        raise EmbeddingError(
            "The Gemini embedding request timed out after "
            f"{settings.GEMINI_TIMEOUT_SECONDS}s."
        ) from exc
    except httpx.HTTPStatusError as exc:
        # Status only. The body of a rejected call quotes back the text that was
        # sent, which here is knowledge base content.
        raise EmbeddingError(
            f"Gemini rejected the embedding request: HTTP {exc.response.status_code}."
        ) from exc
    except httpx.HTTPError as exc:
        raise EmbeddingError(f"The Gemini embedding request failed: {exc}") from exc
    except ValueError as exc:
        # A 200 whose body is not JSON at all — a proxy's error page, say.
        raise EmbeddingError("Gemini returned a response that is not JSON.") from exc

    try:
        embeddings: list[list[float]] = [item["values"] for item in body["embeddings"]]
    except (KeyError, TypeError) as exc:
        raise EmbeddingError(
            "Gemini returned a response without the expected embeddings."
        ) from exc

    if len(embeddings) != len(texts):
        raise EmbeddingError(
            f"Gemini returned {len(embeddings)} embeddings for {len(texts)} "
            "texts. Refusing to store chunks against the wrong vectors."
        )

    # The width, checked here rather than discovered by the INSERT. A model
    # that ignores outputDimensionality, or a GEMINI_EMBED_MODEL that cannot
    # produce 768 at all, otherwise fails as a database error inside
    # index_entry() — which the endpoint treats as "saved but not indexed" and
    # only logs. Named at the boundary, the log says which setting is wrong.
    wrong = next((len(e) for e in embeddings if len(e) != EMBEDDING_DIMENSIONS), None)
    if wrong is not None:
        raise EmbeddingError(
            f"{settings.GEMINI_EMBED_MODEL} returned a {wrong}-dimension "
            f"embedding; the stored column is vector({EMBEDDING_DIMENSIONS}). "
            "Check GEMINI_EMBED_MODEL."
        )
    return embeddings


# ---------------------------------------------------------------------------
# Indexing and retrieval
# ---------------------------------------------------------------------------


def index_entry(db: Session, entry: AgentKnowledgeEntry) -> None:
    """Rebuild every chunk of `entry` from its current content.

    Rebuild rather than a diff of what changed: chunk boundaries move when the
    text around them moves, so "which chunks changed" is not a smaller question
    than "what are the chunks now". It is also what keeps
    UNIQUE(entry_id, chunk_index) from ever blocking a re-run, including one
    after a failure that left an earlier set behind.

    Three steps, in this order, and each boundary is deliberate:

    1. Delete the old chunks and **commit**. Whatever happens next, the entry is
       never answering from text its author has already replaced. An edit is
       often a correction, and the failure mode worth avoiding is a professional
       fixing a wrong statement, being told it saved, and having the wrong one
       keep being quoted.
    2. Embed, with no transaction open. A multi-second call to a third party
       must not sit inside one holding row locks — the same rule that makes this
       function an explicit call rather than an ORM event.
    3. Insert the new chunks and commit.

    Between (1) and (3) the entry is not retrievable. That window is the price
    of never serving retracted content, and a failed run leaves the entry in it:
    saved, editable, and not yet searchable until the next PATCH re-indexes it.

    Two edits of the same entry landing at once are left to the unique
    constraint rather than to a lock. Both delete, both insert, and the second
    commit fails on UNIQUE(entry_id, chunk_index) — the endpoint logs it as an
    unindexed entry. The cost is an index built from the older of two texts
    that were saved seconds apart; the alternative is a lock held across the
    embedding call, which is the one thing the ordering above exists to avoid.

    Commits — twice. Called from the endpoint after the entry itself is
    committed.
    """
    db.execute(
        delete(AgentKnowledgeChunk).where(AgentKnowledgeChunk.entry_id == entry.id)
    )
    db.commit()

    texts = chunk_text(entry.content)
    # Each chunk is embedded with the entry's title in front of it, and stored
    # without it. A paragraph usually assumes the subject its heading already
    # named — "הזכאות ניתנת עד גובה 100% מהתעריף" says nothing about ארנונה on
    # its own — so a chunk embedded alone can lose to an unrelated entry built
    # from the same generic words. What gets stored stays the paragraph, so a
    # citation quotes the source rather than a heading the author never wrote
    # there.
    #
    # This is why update_knowledge_entry() re-indexes on a title change too: a
    # title that reaches an embedding is a title that has to be kept current in
    # one.
    embeddings = embed_texts(
        [f"{entry.title}\n\n{text}" for text in texts], TASK_TYPE_DOCUMENT
    )

    db.add_all(
        [
            AgentKnowledgeChunk(
                entry_id=entry.id,
                chunk_text=text,
                chunk_index=index,
                embedding=embedding,
            )
            for index, (text, embedding) in enumerate(
                zip(texts, embeddings, strict=True)
            )
        ]
    )
    db.commit()


@dataclass(frozen=True)
class RetrievedChunk:
    """One retrieved passage, with the entry it came from.

    Part of retrieve()'s contract, and imported by ABF-122 (the agent chat
    flow) — not dead code, though nothing outside this module names it yet.
    Deliberately a plain dataclass and not the chunk ORM row, so ABF-122 is not
    coupled to the chunk table's schema.

    `content` is the chunk's own text, not the whole entry — that is the point
    of chunking. `title`, `source_name` and `source_url` come from the parent
    entry, so an answer built on this can say where the passage came from.
    """

    title: str
    content: str
    source_name: str | None
    source_url: str | None

    # 1 - cosine distance. Inverted here rather than passed on as a distance so
    # that "higher is better" holds for every caller, which is the direction a
    # relevance score is read in.
    #
    # Range is -1.0 to 1.0, not 0.0 to 1.0: cosine distance runs to 2.0 for
    # vectors pointing opposite ways. 1.0 is identical, 0.0 unrelated, negative
    # actively contrary. Worth knowing before a caller treats this as a
    # percentage or applies a threshold to it.
    score: float


def retrieve(
    db: Session,
    domain_id: str,
    query: str,
    k: int = 5,
) -> list[RetrievedChunk]:
    """Return the `k` chunks of `domain_id` closest in meaning to `query`.

    Scoped to one domain by construction: a chunk from another domain cannot be
    reached through this function at all, whatever the query says.

    A domain with nothing indexed returns an empty list — a knowledge base still
    being filled in is a normal state, not an error.
    """
    if not query.strip():
        return []

    query_embedding = embed_text(query, TASK_TYPE_QUERY)

    # Exact scan, ordered in the database: pgvector computes the distance over
    # this domain's chunks and returns only the k nearest, so neither the
    # embeddings nor the rows behind them travel to the application.
    distance = AgentKnowledgeChunk.embedding.cosine_distance(query_embedding)
    rows = db.execute(
        select(
            AgentKnowledgeEntry.title,
            AgentKnowledgeChunk.chunk_text,
            AgentKnowledgeEntry.source_name,
            AgentKnowledgeEntry.source_url,
            distance.label("distance"),
        )
        .join(
            AgentKnowledgeEntry,
            AgentKnowledgeChunk.entry_id == AgentKnowledgeEntry.id,
        )
        .where(AgentKnowledgeEntry.domain_id == domain_id)
        .order_by(distance)
        .limit(k)
    ).all()

    return [
        RetrievedChunk(
            title=row.title,
            content=row.chunk_text,
            source_name=row.source_name,
            source_url=row.source_url,
            score=1.0 - float(row.distance),
        )
        for row in rows
    ]
