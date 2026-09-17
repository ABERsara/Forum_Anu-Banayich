"""
AI agent service — the domain catalog and its knowledge base (ABF-120/121),
and the conversation flow (ABF-122).

get_visible_domains() applies the same group/sector visibility filter as the
forum (see forum_service._content_filter): a domain is visible to a user when
its group_visibility matches the user's group or is "all", AND its
sector_visibility matches the user's sector or is "all". Inactive domains are
never returned.

The knowledge-base side answers a different question. Reading the catalog asks
"which domains is this member offered"; editing a knowledge base asks "may this
professional edit this one", and the answer turns on their discipline, not on
their bereavement group — an admin and a professional have neither user_type
nor sector at all. The write functions own the whole operation: the commit, and
whether the edit earns a re-index. The endpoints authorize and hand off, so
none of this is reachable only through a request.

The chat side (ABF-122) is where the pieces meet — retrieval (rag_service),
generation (llm_service), the conversation rows (ABF-120) and the audit entry.
It lives here rather than in the endpoints so that those stay what
CONTRIBUTING §2 asks an endpoint to be: receive, validate shape, delegate,
return.

Four rules are enforced here rather than in the prompt, because a prompt is a
request and these are guarantees:

* **A domain is resolved through visibility, never taken from the URL.** Since
  ABF-120 an agent is a table row gated by group/sector exactly like a forum
  post, so `{domain_id}` is an id to be checked, not an enum FastAPI can
  validate for us. See get_visible_domain().
* **No material, no answer.** When nothing clears
  settings.AGENT_MIN_RELEVANCE_SCORE the provider is not called at all — the
  agent says it has nothing and points at human advice. The model never gets
  the chance to fill a void.
* **The disclaimer is always there.** It is concatenated onto the answer, not
  asked for, so it cannot be dropped or paraphrased away.
* **A follow-up is read next to the question before it.** "וכמה זה בערך?"
  names nothing on its own, so retrieval that only sees those four words finds
  nothing near enough, and the agent would refer the user to a human one turn
  after answering the very question being followed up on. See _retrieve_for().

Message content is encrypted at rest, the same way DirectMessage.content is
(AES-256-GCM, app/core/encryption.py) and for the same reason: on a
bereavement platform a question put to an agent routinely carries personal
disclosure — finances, custody, health, who died. ABF-120 put `key_version` on
the model for exactly this; ABF-122 is what fills it in. Nothing outside this
module handles ciphertext and nothing outside it is handed a raw row:
_to_message() decrypts on the way out.

Nothing written to the audit log describes what was said. The AuditLog row
records that a conversation happened, whose it was, and how well grounded the
answer was — SPEC §9.3 wants the trail, not the transcript. Access that was
*refused* is logged too, and access that was granted is not; see _deny().
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from cryptography.exceptions import InvalidTag
from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    AgentMessageRole,
    AuditAction,
    GroupVisibility,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.encryption import decrypt_message, encrypt_message
from app.core.i18n import translate
from app.models.agent import (
    AgentConversation,
    AgentDomain,
    AgentKnowledgeEntry,
    AgentMessage,
)
from app.models.user import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentConversationResponse,
    AgentKnowledgeEntryCreate,
    AgentKnowledgeEntryUpdate,
    AgentMessageResponse,
    AgentSourceResponse,
)
from app.services import llm_service, rag_service
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

# The only two fields an embedding is built from. index_entry() embeds each
# chunk with the title in front of it, so a title left unindexed would go on
# being searched for under the old one — which is worse than not indexing it at
# all. A source_name or source_url fix changes nothing an embedding sees, and
# must not spend a paid round trip rebuilding identical vectors.
_INDEXED_FIELDS = frozenset({"title", "content"})

#: The rate limit is "per day" in the sense of a rolling 24 hours, not of a
#: calendar day: a midnight reset would let one user spend two days' budget in
#: a few minutes either side of it.
RATE_LIMIT_WINDOW = timedelta(hours=24)

#: How _compose_answer() joins an answer to ANSWER_DISCLAIMER — and therefore
#: how _without_disclaimer() takes it back off. Named once so the two cannot
#: drift apart and leave the disclaimer stuck in the history.
DISCLAIMER_SEPARATOR = "\n\n"

#: The detail behind a failed decrypt. A literal key rather than translate(),
#: matching forum_service._to_response_dict() exactly: this particular key is
#: already in the client's KNOWN_ERROR_KEYS and resolved there, so sending
#: finished prose instead would drop the screen to its generic fallback.
#: Unifying the two mechanisms needs a frontend change and is a ticket of its
#: own — see app/core/messages.py's docstring.
_DECRYPTION_FAILED = "errors.internal_server_error"


def _utc_now() -> datetime:
    """Naive UTC, matching how every datetime column in the schema is read."""
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Which agents a member may talk to
# ---------------------------------------------------------------------------


def _visibility_clauses(
    user_type: UserType, sector: Sector
) -> tuple[ColumnElement[bool], ...]:
    """The DB-side group/sector rule, shared by the list and the single lookup.

    Mirrors forum_service._content_filter:

        (group_visibility == user's group  OR  group_visibility == ALL)
        AND
        (sector_visibility == user's sector  OR  sector_visibility == ALL)

    Takes the two values rather than the User, because they are Optional on
    User and the two callers answer a caller who is missing them in different
    ways — one raises, one 404s. Passing them in puts that decision at the
    call site instead of asserting it here.
    """
    return (
        or_(
            AgentDomain.group_visibility == GroupVisibility(user_type.value),
            AgentDomain.group_visibility == GroupVisibility.ALL,
        ),
        or_(
            AgentDomain.sector_visibility == SectorVisibility(sector.value),
            AgentDomain.sector_visibility == SectorVisibility.ALL,
        ),
    )


def get_visible_domains(db: Session, user: User) -> list[AgentDomain]:
    """
    Return the active agent domains this user may see, ordered by lower(name)
    then id — deterministic, and case-insensitive for Latin names. Hebrew
    ordering still depends on the DB collation (SQLite compares code points,
    Postgres uses its locale), which is cosmetic here: the catalog is a
    handful of domains.

    user_type/sector are Optional on User (other roles don't have them). The
    only caller, GET /agents, is gated by require_role(UserRole.USER), so they
    are always set here; check it rather than let a non-USER caller hit a
    confusing AttributeError inside the filter.
    """
    if user.user_type is None:
        raise ValueError("get_visible_domains() requires a user with user_type set")
    if user.sector is None:
        raise ValueError("get_visible_domains() requires a user with sector set")
    return (
        db.query(AgentDomain)
        .filter(
            AgentDomain.is_active.is_(True),
            *_visibility_clauses(user.user_type, user.sector),
        )
        .order_by(func.lower(AgentDomain.name), AgentDomain.id)
        .all()
    )


def get_visible_domain(db: Session, user: User, domain_id: str) -> AgentDomain:
    """One agent a member may use, by id, or 404 — the IDOR guard for every
    member-facing `{domain_id}` route.

    ABF-120 shipped only the plural `get_visible_domains()`, for the catalog
    screen. Every member-facing endpoint that takes an id needs the singular
    one: a `{domain_id}` in a URL is a guess until it has been resolved against
    the caller's own group/sector, and without this a member could reach an
    agent built for a different group by pasting its id.

    **404, never 403, and the same 404 for all four ways of failing** — no such
    id, a domain of another group, of another sector, or one that is
    deactivated. A reader who may not use an agent must not be able to tell
    "there is no such agent" from "there is one and it is not for you"; on a
    platform segmented by sector, that difference is itself information about
    the community. This is forum_service.get_post_by_id's rule for a row whose
    existence the caller may not learn.

    ADMIN resolves by id alone, with no visibility filter and no `is_active`
    filter. An admin has no user_type/sector to filter by, and the reason an
    admin is here at all is the audit trail: an AuditLog row pointing at a
    conversation in a since-deactivated domain still has to open. Every other
    non-USER role gets the same 404 as a stranger — a moderator has no business
    inside a member's agent thread (SPEC §9.3).

    Not a duplicate of get_domain_or_404() below; the two ask different
    questions. This one asks "may this member *use* this agent", and hides
    every reason for no behind one 404. That one asks "which domain is being
    edited", for the admins and professionals who have no group or sector to be
    filtered by, and for whom `is_active` is beside the point — a retired
    agent's knowledge base still has to be correctable.
    """
    query = db.query(AgentDomain).filter(AgentDomain.id == domain_id)

    if user.role != UserRole.ADMIN:
        if user.role != UserRole.USER or user.user_type is None or user.sector is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=translate("agents.domain_not_found"),
            )
        query = query.filter(
            AgentDomain.is_active.is_(True),
            *_visibility_clauses(user.user_type, user.sector),
        )

    domain = query.first()
    if domain is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate("agents.domain_not_found"),
        )
    return domain


# ---------------------------------------------------------------------------
# Who may maintain a knowledge base
# ---------------------------------------------------------------------------


def get_domain_or_404(db: Session, domain_id: str) -> AgentDomain:
    """Load one domain by id, or raise 404.

    Unfiltered on purpose. get_visible_domains() above raises ValueError for a
    user without user_type/sector, which is every admin and every professional —
    the two roles this lookup exists for.

    404 rather than 403 for an id that does not exist: a 403 would confirm that
    some other domain is there, which is the difference between refusing a
    request and answering a question about the catalog that was not asked.
    """
    domain = db.get(AgentDomain, domain_id)
    if domain is None:
        raise HTTPException(
            status_code=404, detail=translate("agents.domain_not_found")
        )
    return domain


def can_manage_knowledge(user: User, domain: AgentDomain) -> bool:
    """May this user add to or edit this domain's knowledge base?

    Admins may edit any domain. A professional may edit the domains of their own
    discipline: a lawyer maintains the legal-rights agent, not the medical one.

    The role is checked as well as the discipline, though today every user with
    a professional_domain set is a professional. professional_domain is nullable
    and lives on User rather than on a professionals-only table, so the day it
    is set on anyone else — an admin's own area of expertise, a moderator's —
    that alone must not hand them an editor's rights.
    """
    if user.role == UserRole.ADMIN:
        return True
    return (
        user.role == UserRole.PROFESSIONAL
        and user.professional_domain is not None
        and user.professional_domain == domain.professional_domain
    )


def get_manageable_domain(db: Session, domain_id: str, user: User) -> AgentDomain:
    """The domain `user` is allowed to manage, or the right refusal.

    404 when it does not exist, 403 when it does but is not theirs — in that
    order, so the two questions stay separate and neither leaks the other.
    """
    domain = get_domain_or_404(db, domain_id)
    if not can_manage_knowledge(user, domain):
        raise HTTPException(
            status_code=403, detail=translate("agents.knowledge_manage_forbidden")
        )
    return domain


def get_manageable_domains(db: Session, user: User) -> list[AgentDomain]:
    """Every domain whose knowledge base `user` may maintain, by name.

    Filtered through can_manage_knowledge() itself rather than a query that
    restates it, so the list a screen offers and the writes the API accepts
    cannot drift apart. The catalog is a handful of rows, one per subject, so
    loading it whole costs nothing.

    Inactive domains are included: retiring an agent hides it from members, not
    from the people who maintain it, and the knowledge endpoints accept writes
    to it either way.
    """
    domains = db.query(AgentDomain).order_by(AgentDomain.name, AgentDomain.id).all()
    return [domain for domain in domains if can_manage_knowledge(user, domain)]


def list_knowledge_entries(
    db: Session,
    domain_id: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AgentKnowledgeEntry], int]:
    """One page of a domain's knowledge base, newest edit first, and the total.

    Whether the caller may read it is get_manageable_domain()'s question, and is
    settled before this is called.
    """
    query = db.query(AgentKnowledgeEntry).filter(
        AgentKnowledgeEntry.domain_id == domain_id
    )
    total = query.count()

    rows = (
        # id as a tiebreaker: two entries saved in the same second share an
        # updated_at, and without a total order a row can repeat across pages
        # or be skipped.
        query.order_by(AgentKnowledgeEntry.updated_at.desc(), AgentKnowledgeEntry.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def get_entry_or_404(db: Session, domain_id: str, entry_id: str) -> AgentKnowledgeEntry:
    """Load an entry *of this domain*, or raise 404.

    Both ids are in the path, and only the domain one has been authorized by the
    time this runs. Matching on the pair is what stops a professional from
    pairing their own domain_id with an entry_id belonging to someone else's
    domain and editing it. An entry that exists under a different domain is a
    404 here, exactly like one that does not exist.
    """
    entry = (
        db.query(AgentKnowledgeEntry)
        .filter(
            AgentKnowledgeEntry.id == entry_id,
            AgentKnowledgeEntry.domain_id == domain_id,
        )
        .first()
    )
    if entry is None:
        raise HTTPException(
            status_code=404, detail=translate("agents.knowledge_entry_not_found")
        )
    return entry


# ---------------------------------------------------------------------------
# Writing a knowledge base
# ---------------------------------------------------------------------------


def index_entry_safe(db: Session, entry: AgentKnowledgeEntry) -> None:
    """Re-index one entry, without letting a failed index fail the write.

    The entry is already committed by the time this runs, and it is the
    professional's work. Reporting a 500 for it because Google was unreachable
    would be the worse outcome by far — the write did happen, and the caller
    would be told it did not. An unindexed entry is saved, visible and editable,
    and the next edit that touches its title or content indexes it. So this logs
    and returns.

    SQLAlchemyError is caught alongside EmbeddingError because index_entry()
    commits: a deadlock or a dropped connection on either commit is exactly as
    survivable as a failed embedding, and leaves the session needing a rollback
    before the request can be answered at all.
    """
    try:
        rag_service.index_entry(db, entry)
    except (rag_service.EmbeddingError, SQLAlchemyError):
        db.rollback()
        logger.exception(
            "Knowledge entry %s was saved but could not be indexed; it will not "
            "be retrievable until it is edited again.",
            entry.id,
        )


def create_knowledge_entry(
    db: Session,
    domain_id: str,
    data: AgentKnowledgeEntryCreate,
    author: User,
) -> AgentKnowledgeEntry:
    """Add an entry to a domain's knowledge base and index it for retrieval.

    `domain_id` comes from the path and `author` from the token, never from the
    body: both are the caller's authorization, not their claim. Whether this
    caller may write to this domain is get_manageable_domain()'s question, and
    is settled before this is called.

    Indexing runs after the commit, never inside it — index_entry() makes an
    HTTP call, and a transaction held open across it would hold row locks for
    the length of a network round trip.
    """
    entry = AgentKnowledgeEntry(
        domain_id=domain_id,
        updated_by=author.id,
        **data.model_dump(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    index_entry_safe(db, entry)
    return entry


def update_knowledge_entry(
    db: Session,
    entry: AgentKnowledgeEntry,
    data: AgentKnowledgeEntryUpdate,
    editor: User,
) -> AgentKnowledgeEntry:
    """Edit a knowledge base entry, re-indexing it only if its meaning changed.

    Only the fields actually present in the body are written, which is what lets
    a source be corrected without re-sending the content — and, because
    re-indexing turns on which fields arrived, without paying for a round of
    embeddings that would produce identical chunks.
    """
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(entry, field, value)
    entry.updated_by = editor.id
    db.commit()
    db.refresh(entry)

    if changes.keys() & _INDEXED_FIELDS:
        index_entry_safe(db, entry)
    return entry


def delete_knowledge_entry(db: Session, entry: AgentKnowledgeEntry) -> None:
    """Remove a knowledge base entry; its chunks go with it.

    The chunks are deleted by the relationship's delete-orphan cascade, so
    nothing is left behind to be retrieved and quoted after the entry that said
    it is gone.
    """
    db.delete(entry)
    db.commit()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def messages_left_today(db: Session, user: User) -> int:
    """Questions `user` may still put to the agents in the current window.

    Counts the user's own turns only — the agent's replies are not the user's
    doing, and counting them would silently halve the quota — and counts them
    across every domain, because the cost this caps is one provider bill and
    not one agent's.
    """
    since = _utc_now() - RATE_LIMIT_WINDOW
    used = (
        db.query(AgentMessage)
        .join(AgentConversation, AgentMessage.conversation_id == AgentConversation.id)
        .filter(
            AgentConversation.user_id == user.id,
            AgentMessage.role == AgentMessageRole.USER,
            AgentMessage.created_at >= since,
        )
        .count()
    )
    return max(0, settings.AGENT_RATE_LIMIT_PER_DAY - used)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


def chat(
    db: Session,
    user: User,
    domain_id: str,
    data: AgentChatRequest,
) -> AgentChatResponse:
    """Answer one question and record the exchange.

    Order matters. The domain is resolved — and the caller's right to it
    checked — first; then retrieval and generation happen *before* anything is
    written. A provider timeout therefore leaves no half-conversation behind
    and does not spend one of the user's daily messages, because the rate
    limit counts rows and no row was written.
    """
    domain = get_visible_domain(db, user, domain_id)
    conversation = _load_own_conversation(db, user, domain, data.conversation_id)
    history = _recent_turns(db, conversation)

    # Stamped before the provider is called, so the question keeps the time it
    # was asked rather than the time the answer came back.
    asked_at = _utc_now()
    try:
        chunks = _retrieve_for(db, domain, data.message, history)
    except rag_service.EmbeddingError:
        # The question could not be embedded, so retrieval never ran. Storing
        # the "I have nothing on that" reply would be a lie about the knowledge
        # base and would sit in the member's thread forever; the outage is
        # ours, and it says so.
        logger.warning("Agent retrieval failed: the question could not be embedded")
        raise _unavailable() from None
    answer = _compose_answer(domain, data.message, chunks, history)
    answered_at = _utc_now()

    if conversation is None:
        # Both timestamps are given here rather than left to their
        # `server_default` and then overwritten: assigning an attribute marks
        # it dirty whatever its current value, so setting last_message_at
        # after the INSERT would cost every new thread a pointless UPDATE.
        conversation = AgentConversation(
            user_id=user.id,
            domain_id=domain.id,
            started_at=asked_at,
            last_message_at=answered_at,
        )
        db.add(conversation)
        db.flush()  # assigns conversation.id, needed by both messages below
    else:
        # Adding children does not touch the parent row, and ABF-120's column
        # has no `onupdate` — nothing else would move this. It is what orders
        # a member's threads by last activity in ABF-123.
        conversation.last_message_at = answered_at

    question_row = _new_message(
        conversation, AgentMessageRole.USER, data.message, asked_at
    )
    answer_row = _new_message(conversation, AgentMessageRole.AGENT, answer, answered_at)
    db.add_all([question_row, answer_row])
    db.flush()  # assigns both message ids

    # Built before log_action() commits. Afterwards these rows are expired, so
    # every attribute read below would be a fresh SELECT — and `content` would
    # come back as ciphertext, needing a decrypt for plaintext already in hand.
    response = AgentChatResponse(
        conversation_id=conversation.id,
        question=AgentMessageResponse(
            id=question_row.id,
            role=AgentMessageRole.USER,
            content=data.message,
            created_at=asked_at,
        ),
        answer=AgentMessageResponse(
            id=answer_row.id,
            role=AgentMessageRole.AGENT,
            content=answer,
            created_at=answered_at,
        ),
        sources=_to_sources(chunks),
    )

    # log_action() commits, which persists the two messages above with it.
    # Details carry no message text: how many passages grounded the answer,
    # and which agent it was. Nothing that was said.
    log_action(
        db,
        actor=user,
        action=AuditAction.AGENT_CONVERSATION,
        entity_type="AgentConversation",
        entity_id=conversation.id,
        details={
            "domain_id": domain.id,
            "retrieved_chunks": len(chunks),
            "answered_from_knowledge_base": bool(chunks),
            "llm_provider": settings.LLM_PROVIDER,
        },
    )
    return response


def get_conversation(
    db: Session,
    user: User,
    domain_id: str,
    conversation_id: str,
) -> AgentConversationResponse:
    """One thread, messages oldest first.

    Readable by its owner and by an ADMIN — the audit trail is admin-visible
    and a conversation it points at has to be reachable from it. Everyone else
    gets 403, including a user who guessed a valid id.

    The 404/403 split is the one get_visible_domain() explains. A domain the
    caller may not see is a 404 (they may not learn it exists), and so is a
    conversation that is not in that domain. A conversation that *is* there,
    under an agent this caller is entitled to use, and simply belongs to
    someone else is a 403: that is the permission axis rather than the
    existence one — the ticket's acceptance criterion, and how
    forum_service.get_post_by_id treats a post that exists and is visible but
    is barred on group/sector.

    One consequence worth naming: a member whose group or sector changed, or
    whose agent has been deactivated, gets 404 on her own old threads, because
    get_visible_domain() runs first. That is the decision recorded on the
    ticket, and it is why ABF-123 should reach threads through the domains
    GET /agents returns rather than from a standalone history screen.

    Returned whole, without the cursor paging forum_service gives a direct-
    message conversation. A DM thread is two people talking for years and is
    capped at MAX_MESSAGES_PER_CONVERSATION; an agent thread is one sitting,
    bounded by AGENT_RATE_LIMIT_PER_DAY, and ABF-123 renders it in one go —
    paging it now would be an API a screen has not asked for. The cost being
    watched is decryption per request, so if ABF-123 does keep a single thread
    alive across sessions, this is where a cursor goes.
    """
    domain = get_visible_domain(db, user, domain_id)
    conversation = _get_conversation_in_domain(db, domain, conversation_id)

    if conversation.user_id != user.id and user.role != UserRole.ADMIN:
        _deny(db, user, conversation_id, reason="read_blocked")

    messages = (
        # `id` only breaks a tie in `created_at`. Rows this service writes
        # cannot tie — _new_message() stamps them microseconds apart — but a
        # row inserted by a fixture or a backfill can, and a thread must not
        # render in a different order on two requests.
        db.query(AgentMessage)
        .filter(AgentMessage.conversation_id == conversation.id)
        .order_by(AgentMessage.created_at, AgentMessage.id)
        .all()
    )
    return AgentConversationResponse(
        id=conversation.id,
        domain_id=conversation.domain_id,
        started_at=conversation.started_at,
        last_message_at=conversation.last_message_at,
        messages=[_to_message(message) for message in messages],
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _new_message(
    conversation: AgentConversation,
    role: AgentMessageRole,
    content: str,
    created_at: datetime,
) -> AgentMessage:
    """One agent_messages row: content encrypted, timestamp explicit.

    `created_at` is passed rather than left to the column's `server_default`
    for two reasons. It is what orders a thread, and the two rows of one
    exchange are inserted together: on SQLite `func.now()` has one-second
    resolution, so both would land on the same value and "question before
    answer" would become whatever order the rows happen to come back in. And
    the rolling quota window compares `created_at` against `_utc_now()`, so
    the stored value has to come from the same clock as the threshold —
    otherwise a DB server not running in UTC skews the window.
    """
    ciphertext, key_version = encrypt_message(content)
    return AgentMessage(
        conversation_id=conversation.id,
        role=role,
        content=ciphertext,
        key_version=key_version,
        created_at=created_at,
    )


def _plaintext(message: AgentMessage) -> str:
    """What one stored row actually says.

    The single place ciphertext becomes text — used both by the API mapping
    below and by _recent_turns(), which needs the words and not a response
    object. The plaintext is never written back onto the ORM instance: that
    instance is session-tracked, and a decrypted value assigned to `content`
    could be flushed back to the DB by some later, unrelated commit, silently
    replacing the ciphertext. The same reasoning as
    forum_service._to_response_dict().

    AES-GCM's InvalidTag means the row failed authentication (DB corruption,
    or content encrypted under a different key). It surfaces as a generic 500,
    so that neither the failure detail nor the fact that it was specifically a
    decryption failure reaches the client.
    """
    try:
        return decrypt_message(message.content, message.key_version)
    except InvalidTag as exc:
        logger.error("Failed to decrypt agent message %s", message.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_DECRYPTION_FAILED,
        ) from exc


def _to_message(message: AgentMessage) -> AgentMessageResponse:
    """One stored row as the API returns it, decrypted."""
    return AgentMessageResponse(
        id=message.id,
        role=message.role,
        content=_plaintext(message),
        created_at=message.created_at,
    )


def _deny(db: Session, user: User, conversation_id: str, reason: str) -> NoReturn:
    """Refuse access to a conversation, and leave a trace that it was refused.

    Denied access is logged and granted access is not — the same asymmetry
    forum_service applies to direct messages, and for the same reason: a
    conversation someone was blocked from reading is the event worth being
    able to look up later. `reason` says which door was tried; nothing about
    the thread's content is recorded, only its id.
    """
    log_action(
        db,
        actor=user,
        action=AuditAction.AGENT_CONVERSATION_ACCESS_DENIED,
        entity_type="AgentConversation",
        entity_id=conversation_id,
        details={"reason": reason},
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=translate("agents.conversation_forbidden"),
    )


def _get_conversation_in_domain(
    db: Session, domain: AgentDomain, conversation_id: str
) -> AgentConversation:
    """Load a conversation, or 404.

    A conversation of another domain is 404 rather than 403: under this
    agent's URL it genuinely does not exist, and saying otherwise would
    confirm an id to someone who only guessed it.
    """
    conversation = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.id == conversation_id,
            AgentConversation.domain_id == domain.id,
        )
        .first()
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate("agents.conversation_not_found"),
        )
    return conversation


def _load_own_conversation(
    db: Session,
    user: User,
    domain: AgentDomain,
    conversation_id: str | None,
) -> AgentConversation | None:
    """The thread a new question continues, or None to start a fresh one.

    Writing is owner-only — an ADMIN may *read* someone's conversation but
    never add a turn to it, because every message in a thread has to be
    something its owner actually said.
    """
    if conversation_id is None:
        return None

    conversation = _get_conversation_in_domain(db, domain, conversation_id)
    if conversation.user_id != user.id:
        _deny(db, user, conversation_id, reason="write_blocked")
    return conversation


def _recent_turns(
    db: Session, conversation: AgentConversation | None
) -> list[llm_service.HistoryTurn]:
    """The last AGENT_HISTORY_TURNS exchanges, oldest first, decrypted.

    A turn is a question and the answer it got, so the window is up to twice
    as many rows. Fetching newest-first and reversing keeps the LIMIT on the
    end of the table that matters — an old conversation should not get slower
    to continue than a new one.
    """
    if conversation is None:
        return []

    message_budget = 2 * max(0, settings.AGENT_HISTORY_TURNS)
    if message_budget == 0:
        return []

    recent = (
        db.query(AgentMessage)
        .filter(AgentMessage.conversation_id == conversation.id)
        # Same tie-break as get_conversation(), mirrored: whatever order that
        # renders the thread in is the order it is replayed to the model in.
        .order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc())
        .limit(message_budget)
        .all()
    )
    return [
        llm_service.HistoryTurn(
            role=message.role,
            content=_without_disclaimer(_plaintext(message)),
        )
        for message in reversed(recent)
    ]


def _without_disclaimer(content: str) -> str:
    """An earlier turn as the prompt should see it.

    Every stored agent turn ends in ANSWER_DISCLAIMER, and replaying that back
    would contradict the rule telling the model not to write one, besides
    paying for the same paragraph again on every follow-up. Removed exactly as
    _compose_answer() attached it, so a passage that merely quotes the
    disclaimer mid-answer is left alone.
    """
    return content.removesuffix(DISCLAIMER_SEPARATOR + llm_service.ANSWER_DISCLAIMER)


def _retrieve(
    db: Session, domain: AgentDomain, query: str
) -> list[rag_service.RetrievedChunk]:
    """Passages for one query that are actually close enough to quote.

    rag_service.retrieve() is a ranking, not a filter: it returns the k nearest
    chunks of the domain however far away they are, because "nearest" is
    defined for every question ever asked. So a question the knowledge base has
    nothing to say about does not come back empty — it comes back with the five
    least-unrelated paragraphs in it, and an agent that passed those on would be
    answering "מה תחזית מזג האוויר מחר?" out of a document about housing aid.

    settings.AGENT_MIN_RELEVANCE_SCORE is where "nothing relevant" is decided,
    and deciding it here rather than in the prompt is what makes the referral to
    human advice a property of the code: below the floor nothing is sent, the
    provider is never called, and there is no opportunity to invent an answer.

    An embedding failure — no API key, a timeout, Gemini down — raises
    EmbeddingError, which the caller turns into a 503. It is deliberately *not*
    treated as "nothing found": that would store "I have no information on that"
    as the agent's answer to a question the knowledge base may well cover, which
    is a false statement kept forever in a thread the member can re-read.
    """
    return [
        chunk
        for chunk in rag_service.retrieve(db, domain.id, query)
        if chunk.score >= settings.AGENT_MIN_RELEVANCE_SCORE
    ]


def _retrieve_for(
    db: Session,
    domain: AgentDomain,
    message: str,
    history: list[llm_service.HistoryTurn],
) -> list[rag_service.RetrievedChunk]:
    """Passages for this question, read in the light of the one before it.

    A follow-up carries none of its own subject: "וכמה זה בערך?" is four words
    that name nothing, so an embedding of the message alone lands near nothing
    in particular and the agent would answer "I have no information on that"
    one turn after answering the question it is a follow-up to. When that
    happens and there is a conversation behind the message, the search runs
    again with the previous question folded in — the words the follow-up is
    leaning on.

    A fallback rather than the default: a message that already found its own
    material must not have its ranking dragged towards the earlier subject.
    And only the previous *user* turn, because the agent's replies are its own
    words, not a statement of what is being asked about.

    The second search costs a second embedding call, which is why it only runs
    when the first one found nothing worth quoting.
    """
    chunks = _retrieve(db, domain, message)
    if chunks:
        return chunks

    previous = next(
        (
            turn.content
            for turn in reversed(history)
            if turn.role == AgentMessageRole.USER
        ),
        None,
    )
    if previous is None:
        return []
    return _retrieve(db, domain, f"{previous} {message}")


def _to_context_chunk(chunk: rag_service.RetrievedChunk) -> llm_service.ContextChunk:
    """One retrieved passage as a provider is allowed to see it.

    The whole of ABF-122's dependency on rag_service's row type. The `score`
    is dropped here on purpose: how one embedding model's distances are
    distributed is retrieval's business, and a provider handed it could start
    weighting passages by a number that means something different the day
    GEMINI_EMBED_MODEL changes.
    """
    return llm_service.ContextChunk(
        title=chunk.title,
        content=chunk.content,
        source_name=chunk.source_name,
        source_url=chunk.source_url,
    )


def _to_sources(
    chunks: list[rag_service.RetrievedChunk],
) -> list[AgentSourceResponse]:
    """The documents behind an answer, each named once, best match first.

    Retrieval works on chunks, and a long entry can contribute several of them
    to the same answer — so the raw list routinely repeats one title three
    times. What the reader is being shown is where the answer came from, and
    "ביטוח לאומי ×3" says nothing more than "ביטוח לאומי" does. Deduplicated on
    the full provenance triple rather than on the title alone, because two
    entries can share a heading and cite different documents.

    Order is retrieval's, which is relevance order, so the passage that
    answered the question is the first source listed.
    """
    seen: set[tuple[str, str | None, str | None]] = set()
    sources: list[AgentSourceResponse] = []
    for chunk in chunks:
        identity = (chunk.title, chunk.source_name, chunk.source_url)
        if identity in seen:
            continue
        seen.add(identity)
        sources.append(
            AgentSourceResponse(
                title=chunk.title,
                source_name=chunk.source_name,
                source_url=chunk.source_url,
            )
        )
    return sources


def _compose_answer(
    domain: AgentDomain,
    question: str,
    chunks: list[rag_service.RetrievedChunk],
    history: list[llm_service.HistoryTurn],
) -> str:
    """The text stored as the agent's turn, disclaimer included."""
    body = _answer_body(domain, question, chunks, history)
    return f"{body}{DISCLAIMER_SEPARATOR}{llm_service.ANSWER_DISCLAIMER}"


def _answer_body(
    domain: AgentDomain,
    question: str,
    chunks: list[rag_service.RetrievedChunk],
    history: list[llm_service.HistoryTurn],
) -> str:
    """Ask the provider — unless there is nothing to ground an answer in."""
    if not chunks:
        return llm_service.NO_CONTEXT_ANSWER

    try:
        provider = llm_service.get_provider()
        return provider.generate(
            system_prompt=llm_service.build_system_prompt(domain),
            user_message=question,
            context_chunks=[_to_context_chunk(chunk) for chunk in chunks],
            conversation_history=history,
        )
    except llm_service.LLMNotConfiguredError:
        # A deployment problem, not a bad request: material was found and an
        # answer could have been given. Degrading to the "I have nothing"
        # reply would store a sentence that is not true, so this fails loudly.
        logger.error(
            "No usable LLM provider for LLM_PROVIDER=%r", settings.LLM_PROVIDER
        )
        raise _unavailable() from None
    except llm_service.LLMError as exc:
        # The message is deliberately generic and the same for a timeout and
        # for a refusal: which one it was is in the log, not on the screen.
        logger.warning("Agent generation failed: %s", type(exc).__name__)
        raise _unavailable() from None


def _unavailable() -> HTTPException:
    """The one refusal every provider- and embedding-side fault comes back as.

    A 503 rather than a 500: nothing about the request was wrong, and trying
    again in a minute is genuinely the right advice. One message for every
    cause — a timeout, a refusal, a missing key, an unreachable embedding API —
    because which third party is having a bad afternoon is in the log, not
    something a member is owed on screen.
    """
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=translate("agents.unavailable"),
    )
