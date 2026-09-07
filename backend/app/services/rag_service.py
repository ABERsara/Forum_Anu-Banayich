"""
Knowledge-base retrieval for the AI agents (ABF-121).

``retrieve()`` answers one question: which entries of this domain's knowledge
base, if any, bear on what the user asked. Everything the agent is allowed to
say comes from its return value — an empty list is the signal that there is no
grounded answer to give, and agent_service turns that into the referral to
human advice rather than into a guess.

Ownership, and why this file is on the ABF-122 branch
-----------------------------------------------------
**ABF-121 owns this module.** It has no branch yet (checked per CONTRIBUTING
§8: no `ABF-121` ref on origin, no open PR), and ABF-122 cannot be built or
tested without a ``retrieve()`` — an agent with no retrieval has nothing to
answer from. So ABF-122 carries the floor: the signature ABF-121's ticket
specifies, over ABF-120's own ``agent_knowledge_entries`` table, with the
simplest scorer that satisfies the contract (term overlap). If ABF-121 lands
first, delete this file from the branch and nothing else changes.

The contract ABF-122 was written against, and what ABF-121 may still change:

* **Fixed** — ``retrieve(db, domain_id, query, k=DEFAULT_TOP_K)`` returning a
  list, best first, empty when nothing matches; never reading outside
  ``domain_id``.
* **Fixed** — every returned row exposes ``title``, ``content``,
  ``source_name`` and ``source_url``. Those four attributes are all
  agent_service reads (``_to_context_chunk()``), so swapping the row type is
  a change to one function.
* **Free** — the scoring, and where the rows come from. Embedding-based
  ranking over a chunks/embeddings table replaces ``_score()`` and the query
  in ``retrieve()``; no caller notices.
"""

import re
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models.agent import AgentKnowledgeEntry

#: How many passages a prompt gets — ABF-121's ticket says ``k=5``. Enough for
#: an answer to draw on more than one source, few enough that the prompt stays
#: affordable on every turn.
DEFAULT_TOP_K = 5

#: Terms shorter than this match far too much — Hebrew's one- and two-letter
#: prefixes and function words would score every entry in the domain.
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


def _score(entry: AgentKnowledgeEntry, query_terms: Iterable[str]) -> int:
    """How strongly one entry answers the query.

    Substring containment rather than token equality, because Hebrew glues its
    prepositions onto the noun: the question "האם מגיע לי סיוע בדיור?" carries
    the term "בדיור", and the passage titled "סיוע בדיור" has to match it.
    Whole-token comparison would score that pair zero.
    """
    title = entry.title.lower()
    content = entry.content.lower()

    total = 0
    for term in query_terms:
        if term in title:
            total += TITLE_WEIGHT
        elif term in content:
            total += CONTENT_WEIGHT
    return total


def retrieve(
    db: Session,
    domain_id: str,
    query: str,
    k: int = DEFAULT_TOP_K,
) -> list[AgentKnowledgeEntry]:
    """Entries of `domain_id`'s knowledge base relevant to `query`, best first.

    Returns ``[]`` when nothing matches. That is a normal outcome, not an
    error: it is what an off-topic question looks like, and the caller is
    required to treat it as "no grounded answer exists".

    Never reads outside `domain_id` — each agent is confined to its own
    knowledge base (SPEC §12.1), and that confinement is enforced here in the
    query rather than left to the prompt. Visibility of the domain itself is
    the caller's business and is settled before this is reached
    (agent_service.get_visible_domain); this function is given an id it has
    already been decided the reader may use.
    """
    query_terms = _terms(query)
    if not query_terms:
        return []

    # Scoring in Python over the whole domain: a curated knowledge base is
    # tens to hundreds of entries, and the vector similarity ABF-121 replaces
    # this with does not translate into a SQL WHERE either.
    entries = (
        db.query(AgentKnowledgeEntry)
        .filter(AgentKnowledgeEntry.domain_id == domain_id)
        .all()
    )

    scored = [
        (score, entry) for entry in entries if (score := _score(entry, query_terms))
    ]
    # Sort by score only — ties keep the order the DB returned them in, which
    # is stable enough for a prompt and avoids inventing a second criterion.
    scored.sort(key=lambda pair: pair[0], reverse=True)

    return [entry for _, entry in scored[:k]]
