"""
AI agent service — the domain catalog (ABF-120) and the conversation flow
(ABF-122).

One question in, one grounded answer out. This module is where the pieces
meet — retrieval (rag_service, ABF-121), generation (llm_service), the
conversation rows (ABF-120) and the audit entry — and it exists so that the
endpoints stay what CONTRIBUTING §2 asks an endpoint to be: receive, validate
shape, delegate, return.

Four rules are enforced here rather than in the prompt, because a prompt is a
request and these are guarantees:

* **A domain is resolved through visibility, never taken from the URL.** Since
  ABF-120 an agent is a table row gated by group/sector exactly like a forum
  post, so `{domain_id}` is an id to be checked, not an enum FastAPI can
  validate for us. See get_visible_domain().
* **No material, no answer.** When rag_service.retrieve() comes back empty the
  provider is not called at all — the agent says it has nothing and points at
  human advice. The model never gets the chance to fill a void.
* **The disclaimer is always there.** It is concatenated onto the answer, not
  asked for, so it cannot be dropped or paraphrased away.
* **A follow-up is read next to the question before it.** "וכמה זה בערך?"
  names nothing on its own, so retrieval that only sees those four words finds
  nothing and the agent would refer the user to a human one turn after
  answering the very question being followed up on. See _retrieve_for().

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
    AgentMessageResponse,
    AgentSourceResponse,
)
from app.services import llm_service, rag_service
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

#: The rate limit is "per day" in the sense of a rolling 24 hours, not of a
#: calendar day: a midnight reset would let one user spend two days' budget in
#: a few minutes either side of it.
RATE_LIMIT_WINDOW = timedelta(hours=24)

#: How _compose_answer() joins an answer to ANSWER_DISCLAIMER — and therefore
#: how _without_disclaimer() takes it back off. Named once so the two cannot
#: drift apart and leave the disclaimer stuck in the history.
DISCLAIMER_SEPARATOR = "\n\n"

#: Translation keys, not display text: the i18n DoD requires a server error to
#: come back as a key the client resolves through Transloco (he/en), the way
#: forum_service._DM_FORBIDDEN_MESSAGE already does. The agent's *answers* are
#: the opposite case and stay Hebrew — see llm_service.ANSWER_DISCLAIMER.
_DOMAIN_NOT_FOUND = "errors.agent_domain_not_found"
_CONVERSATION_NOT_FOUND = "errors.agent_conversation_not_found"
_CONVERSATION_FORBIDDEN = "errors.agent_conversation_forbidden"
_AGENT_UNAVAILABLE = "errors.agent_unavailable"
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
    """One domain by id, or 404 — the IDOR guard for every `{domain_id}` route.

    ABF-120 shipped only the plural `get_visible_domains()`, for the catalog
    screen. Every endpoint that takes an id needs the singular one: a
    `{domain_id}` in a URL is a guess until it has been resolved against the
    caller's own group/sector, and without this a member could reach an agent
    built for a different group by pasting its id.

    **404, never 403, and the same 404 for all four ways of failing** — no
    such id, a domain of another group, of another sector, or one that is
    deactivated. A reader who may not use an agent must not be able to tell
    "there is no such agent" from "there is one and it is not for you"; on a
    platform segmented by sector, that difference is itself information about
    the community. This is forum_service.get_post_by_id's rule for a row whose
    existence the caller may not learn.

    ADMIN resolves by id alone, with no visibility filter and no `is_active`
    filter. An admin has no user_type/sector to filter by, and the reason an
    admin is here at all is the audit trail: an AuditLog row pointing at a
    conversation in a since-deactivated domain still has to open. Every other
    non-USER role gets the same 404 as a stranger — a moderator has no
    business inside a member's agent thread (SPEC §9.3).
    """
    query = db.query(AgentDomain).filter(AgentDomain.id == domain_id)

    if user.role != UserRole.ADMIN:
        if user.role != UserRole.USER or user.user_type is None or user.sector is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_DOMAIN_NOT_FOUND
            )
        query = query.filter(
            AgentDomain.is_active.is_(True),
            *_visibility_clauses(user.user_type, user.sector),
        )

    domain = query.first()
    if domain is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_DOMAIN_NOT_FOUND
        )
    return domain


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
    entries = _retrieve_for(db, domain, data.message, history)
    answer = _compose_answer(domain, data.message, entries, history)
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
        sources=[AgentSourceResponse.model_validate(entry) for entry in entries],
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
            "retrieved_chunks": len(entries),
            "answered_from_knowledge_base": bool(entries),
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
    ticket ("call it at the start of chat(), get_conversation(), and every
    endpoint that takes {domain_id}"), and it is why ABF-123 should reach
    threads through the domains GET /agents returns rather than from a
    standalone history screen.

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
        status_code=status.HTTP_403_FORBIDDEN, detail=_CONVERSATION_FORBIDDEN
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
            status_code=status.HTTP_404_NOT_FOUND, detail=_CONVERSATION_NOT_FOUND
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


def _retrieve_for(
    db: Session,
    domain: AgentDomain,
    message: str,
    history: list[llm_service.HistoryTurn],
) -> list[AgentKnowledgeEntry]:
    """Passages for this question, read in the light of the one before it.

    A follow-up carries none of its own subject: "וכמה זה בערך?" is four words
    that name nothing, so retrieval on the message alone comes back empty and
    the agent would answer "I have no information on that" one turn after
    answering the question it is a follow-up to. When that happens and there
    is a conversation behind the message, the search runs again with the
    previous question folded in — the words the follow-up is leaning on.

    A fallback rather than the default: a message that already found its own
    material must not have its ranking dragged towards the earlier subject.
    And only the previous *user* turn, because the agent's replies are its own
    words, not a statement of what is being asked about.
    """
    entries = rag_service.retrieve(db, domain.id, message)
    if entries:
        return entries

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
    return rag_service.retrieve(db, domain.id, f"{previous} {message}")


def _to_context_chunk(entry: AgentKnowledgeEntry) -> llm_service.ContextChunk:
    """The four fields a provider is given about one passage.

    The whole of ABF-122's dependency on rag_service's row type: if ABF-121
    ends up returning chunk rows rather than knowledge entries, this is the
    function that changes.
    """
    return llm_service.ContextChunk(
        title=entry.title,
        content=entry.content,
        source_name=entry.source_name,
        source_url=entry.source_url,
    )


def _compose_answer(
    domain: AgentDomain,
    question: str,
    entries: list[AgentKnowledgeEntry],
    history: list[llm_service.HistoryTurn],
) -> str:
    """The text stored as the agent's turn, disclaimer included."""
    body = _answer_body(domain, question, entries, history)
    return f"{body}{DISCLAIMER_SEPARATOR}{llm_service.ANSWER_DISCLAIMER}"


def _answer_body(
    domain: AgentDomain,
    question: str,
    entries: list[AgentKnowledgeEntry],
    history: list[llm_service.HistoryTurn],
) -> str:
    """Ask the provider — unless there is nothing to ground an answer in."""
    if not entries:
        return llm_service.NO_CONTEXT_ANSWER

    try:
        provider = llm_service.get_provider()
        return provider.generate(
            system_prompt=llm_service.build_system_prompt(domain),
            user_message=question,
            context_chunks=[_to_context_chunk(entry) for entry in entries],
            conversation_history=history,
        )
    except llm_service.LLMNotConfiguredError:
        # A deployment problem, not a bad request: material was found and an
        # answer could have been given. Degrading to the "I have nothing"
        # reply would store a sentence that is not true, so this fails loudly.
        logger.error(
            "No usable LLM provider for LLM_PROVIDER=%r", settings.LLM_PROVIDER
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_AGENT_UNAVAILABLE
        ) from None
    except llm_service.LLMError as exc:
        # The message is deliberately generic and the same for a timeout and
        # for a refusal: which one it was is in the log, not on the screen.
        logger.warning("Agent generation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_AGENT_UNAVAILABLE
        ) from None
