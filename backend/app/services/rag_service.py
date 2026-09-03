"""
Knowledge-base retrieval for the AI agents (ABF-121).

``retrieve()`` answers one question: which passages of this domain's knowledge
base, if any, bear on what the user asked. Everything the agent is allowed to
say comes from its return value — an empty list is the signal that there is no
grounded answer to give, and agent_service turns that into the referral to
human advice rather than into a guess.

Scope note for review
---------------------
ABF-122 depends on this function and ABF-121 owns it. The signature below is
the contract ABF-122 was written against and is not expected to change; the
scorer behind it is deliberately the simplest thing that satisfies the
contract — term overlap against the domain's chunks — so that ABF-122 could be
built and tested end to end. Swapping in embedding-based scoring changes the
body of ``_score()`` and nothing else: no caller reads anything but the
returned rows.
"""

import re
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.core.constants import AgentDomain
from app.models.agent_knowledge import AgentKnowledgeChunk

#: How many passages a prompt gets. Enough for an answer to draw on more than
#: one source, few enough that the prompt stays affordable on every turn.
DEFAULT_TOP_K = 4

#: Terms shorter than this match far too much — Hebrew's one- and two-letter
#: prefixes and function words would score every chunk in the domain.
MIN_TERM_LENGTH = 3

#: A title match says more about relevance than a body match: titles are
#: curated headings, bodies are long enough to mention almost anything.
TITLE_WEIGHT = 3
CONTENT_WEIGHT = 1

#: Frequent words that clear MIN_TERM_LENGTH but carry no topic. Kept short on
#: purpose — a long stop list starts removing real query terms.
STOP_TERMS = frozenset(
    {
        # Hebrew — question words and possessives that clear MIN_TERM_LENGTH.
        "האם",
        "כמה",
        "מתי",
        "איפה",
        "איך",
        "למה",
        "אני",
        "שלי",
        "שלו",
        "שלה",
        "עבור",
        "בבקשה",
        "תודה",
        # English — the platform is Hebrew-first, but a term can arrive in
        # either language and the knowledge base quotes both.
        "the",
        "and",
        "for",
        "what",
        "how",
        "can",
        "does",
        "are",
    }
)

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _terms(text: str) -> set[str]:
    """Content words of `text`, lowercased and deduplicated."""
    return {
        word
        for word in (match.group().lower() for match in _WORD_RE.finditer(text))
        if len(word) >= MIN_TERM_LENGTH and word not in STOP_TERMS
    }


def _score(chunk: AgentKnowledgeChunk, query_terms: Iterable[str]) -> int:
    """How strongly one chunk answers the query.

    Substring containment rather than token equality, because Hebrew glues its
    prepositions onto the noun: the question "האם מגיע לי סיוע בדיור?" carries
    the term "בדיור", and the passage titled "סיוע בדיור" has to match it.
    Whole-token comparison would score that pair zero.
    """
    title = chunk.title.lower()
    content = chunk.content.lower()

    total = 0
    for term in query_terms:
        if term in title:
            total += TITLE_WEIGHT
        elif term in content:
            total += CONTENT_WEIGHT
    return total


def retrieve(
    db: Session,
    domain: AgentDomain,
    query: str,
    limit: int = DEFAULT_TOP_K,
) -> list[AgentKnowledgeChunk]:
    """Passages of `domain`'s knowledge base relevant to `query`, best first.

    Returns ``[]`` when nothing matches. That is a normal outcome, not an
    error: it is what an off-topic question looks like, and the caller is
    required to treat it as "no grounded answer exists".

    Never reads outside `domain` — each agent is confined to its own knowledge
    base (SPEC §12), and that confinement is enforced here in the query rather
    than left to the prompt.
    """
    query_terms = _terms(query)
    if not query_terms:
        return []

    # Scoring in Python over the whole domain: a curated knowledge base is
    # tens to hundreds of passages, and the scorer ABF-121 replaces this with
    # (vector similarity) does not translate into a SQL WHERE either.
    chunks = (
        db.query(AgentKnowledgeChunk).filter(AgentKnowledgeChunk.domain == domain).all()
    )

    scored = [
        (score, chunk) for chunk in chunks if (score := _score(chunk, query_terms))
    ]
    # Sort by score only — ties keep the order the DB returned them in, which
    # is stable enough for a prompt and avoids inventing a second criterion.
    scored.sort(key=lambda pair: pair[0], reverse=True)

    return [chunk for _, chunk in scored[:limit]]
