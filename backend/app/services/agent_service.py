"""
AI agent conversation flow (ABF-122).

One question in, one grounded answer out. This module is where the pieces
meet — retrieval (ABF-121), generation (llm_service), the conversation rows
(ABF-120) and the audit entry — and it exists so that the endpoint stays what
CONTRIBUTING §2 asks an endpoint to be: receive, validate shape, delegate,
return.

Two rules are enforced here rather than in the prompt, because a prompt is a
request and these are guarantees:

* **No material, no answer.** When rag_service.retrieve() comes back empty the
  provider is not called at all — the agent says it has nothing and points at
  human advice. The model never gets the chance to fill a void.
* **The disclaimer is always there.** It is concatenated onto the answer, not
  asked for, so it cannot be dropped or paraphrased away.
* **A follow-up is read next to the question before it.** "וכמה זה בערך?"
  names nothing on its own, so retrieval that only sees those four words finds
  nothing and the agent would refer the user to a human one turn after
  answering the very question being followed up on. See _retrieve_for().

Nothing written to the audit log describes what was said. The AuditLog row
records that a conversation happened, whose it was, and how well grounded the
answer was — SPEC §9.3 wants the trail, not the transcript. Access that was
*refused* is logged too, and access that was granted is not; see _deny().
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AgentDomain, AgentMessageRole, AuditAction, UserRole
from app.core.i18n import translate
from app.models.agent import AgentConversation, AgentMessage
from app.models.agent_knowledge import AgentKnowledgeChunk
from app.models.user import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentConversationOut,
    AgentMessageOut,
    AgentSourceOut,
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

#: Catalogue keys, not display text — each is resolved by translate() at the
#: point it is raised, in the language the request asked for. Named once
#: because each is raised from more than one place and the three must not drift.
_CONVERSATION_NOT_FOUND = "agent.conversation_not_found"
_CONVERSATION_FORBIDDEN = "agent.conversation_forbidden"
_AGENT_UNAVAILABLE = "agent.unavailable"


def _utc_now() -> datetime:
    """Naive UTC, matching how every datetime column in the schema is read."""
    return datetime.now(UTC).replace(tzinfo=None)


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
    domain: AgentDomain,
    data: AgentChatRequest,
) -> AgentChatResponse:
    """Answer one question and record the exchange.

    Order matters: retrieval and generation happen *before* anything is
    written. A provider timeout therefore leaves no half-conversation behind
    and does not spend one of the user's daily messages — the rate limit
    counts rows, and no row was written.
    """
    conversation = _load_own_conversation(db, user, domain, data.conversation_id)
    history = _recent_turns(db, conversation)

    # Stamped before the provider is called, so the question keeps the time it
    # was asked rather than the time the answer came back.
    asked_at = _utc_now()
    chunks = _retrieve_for(db, domain, data.message, history)
    answer = _compose_answer(domain, data.message, chunks, history)

    if conversation is None:
        conversation = AgentConversation(user_id=user.id, domain=domain)
        db.add(conversation)
        db.flush()  # assigns conversation.id, needed by both messages below

    question_row = AgentMessage(
        conversation_id=conversation.id,
        role=AgentMessageRole.USER,
        content=data.message,
        created_at=asked_at,
    )
    answer_row = AgentMessage(
        conversation_id=conversation.id,
        role=AgentMessageRole.AGENT,
        content=answer,
        created_at=_utc_now(),
    )
    db.add_all([question_row, answer_row])

    # Adding children does not touch the parent row, so `onupdate` would not
    # fire — and this timestamp is what orders a user's threads by last
    # activity in ABF-123.
    conversation.updated_at = _utc_now()
    db.flush()

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
            "domain": domain.value,
            "retrieved_chunks": len(chunks),
            "answered_from_knowledge_base": bool(chunks),
            "llm_provider": settings.LLM_PROVIDER,
        },
    )
    db.refresh(question_row)
    db.refresh(answer_row)

    return AgentChatResponse(
        conversation_id=conversation.id,
        question=AgentMessageOut.model_validate(question_row),
        answer=AgentMessageOut.model_validate(answer_row),
        sources=[AgentSourceOut.model_validate(chunk) for chunk in chunks],
    )


def get_conversation(
    db: Session,
    user: User,
    domain: AgentDomain,
    conversation_id: str,
) -> AgentConversationOut:
    """One thread, messages oldest first.

    Readable by its owner and by an ADMIN — the audit trail is admin-visible
    and a conversation it points at has to be reachable from it. Everyone
    else gets 403, including a user who guessed a valid id.
    """
    conversation = _get_conversation_in_domain(db, domain, conversation_id)

    if conversation.user_id != user.id and user.role != UserRole.ADMIN:
        _deny(db, user, conversation_id, reason="read_blocked")

    return AgentConversationOut.model_validate(conversation)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


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
        status_code=status.HTTP_403_FORBIDDEN, detail=translate(_CONVERSATION_FORBIDDEN)
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
            AgentConversation.domain == domain,
        )
        .first()
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate(_CONVERSATION_NOT_FOUND),
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
    """The last AGENT_HISTORY_TURNS exchanges, oldest first.

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
        .order_by(AgentMessage.created_at.desc())
        .limit(message_budget)
        .all()
    )
    return [
        llm_service.HistoryTurn(
            role=message.role, content=_without_disclaimer(message.content)
        )
        for message in reversed(recent)
    ]


def _without_disclaimer(content: str) -> str:
    """An earlier turn as the prompt should see it.

    Every stored agent turn ends in ANSWER_DISCLAIMER, and replaying that back
    would contradict the rule that tells the model not to write one — besides
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
) -> list[AgentKnowledgeChunk]:
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
    chunks = rag_service.retrieve(db, domain, message)
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
    return rag_service.retrieve(db, domain, f"{previous} {message}")


def _compose_answer(
    domain: AgentDomain,
    question: str,
    chunks: list[AgentKnowledgeChunk],
    history: list[llm_service.HistoryTurn],
) -> str:
    """The text stored as the agent's turn, disclaimer included."""
    body = _answer_body(domain, question, chunks, history)
    return f"{body}{DISCLAIMER_SEPARATOR}{llm_service.ANSWER_DISCLAIMER}"


def _answer_body(
    domain: AgentDomain,
    question: str,
    chunks: list[AgentKnowledgeChunk],
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
            context_chunks=[
                llm_service.ContextChunk(
                    title=chunk.title, content=chunk.content, source=chunk.source
                )
                for chunk in chunks
            ],
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
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=translate(_AGENT_UNAVAILABLE),
        ) from None
    except llm_service.LLMError as exc:
        # The message is deliberately generic and the same for a timeout and
        # for a refusal: which one it was is in the log, not on the screen.
        logger.warning("Agent generation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=translate(_AGENT_UNAVAILABLE),
        ) from None
