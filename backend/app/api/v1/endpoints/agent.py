"""
AI agent endpoints.

GET  /agents                                     – the agent domains visible to
                                                   the current user
POST /agents/{domain_id}/chat                    – ask an agent a question
GET  /agents/{domain_id}/conversations/{id}      – read a whole conversation

`domain_id` is an agent_domains row id (uuid), not an enum: since ABF-120 an
agent is a table row an admin can add, gated by group/sector like a forum
post. So an unknown or invisible agent cannot be rejected by path coercion —
agent_service.get_visible_domain() resolves it against the caller and answers
404 for "no such agent", "another group's agent" and "deactivated" alike.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.constants import UserRole
from app.core.dependencies import (
    get_current_active_user,
    get_db,
    rate_limit_chat,
    require_role,
)
from app.models.user import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentConversationResponse,
    AgentDomainResponse,
)
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["AI Agent"])


# USER only, deliberately: ADMIN / MODERATOR / PROFESSIONAL get 403 here. This
# is the member-facing catalog, filtered by the caller's group/sector. Catalog
# management and a professional's "domains I maintain" view (SPEC §12.2) belong
# to a later admin-tools ticket and need a different, unfiltered query. Widening
# this dependency later is backward-compatible.
@router.get(
    "",
    response_model=list[AgentDomainResponse],
    dependencies=[Depends(require_role(UserRole.USER))],
)
def list_agent_domains(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[AgentDomainResponse]:
    """Return the agent domains visible to the current user (group/sector filtered)."""
    return [
        AgentDomainResponse.model_validate(domain)
        for domain in agent_service.get_visible_domains(db, current_user)
    ]


# USER only as well, and for a stronger reason than the catalog: writing a turn
# into a conversation means being its owner, and only a USER row carries the
# group/sector an agent is gated on. An ADMIN reads conversations (below) but
# never adds to one.
@router.post(
    "/{domain_id}/chat",
    response_model=AgentChatResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.USER))],
)
def chat(
    domain_id: str,
    data: AgentChatRequest,
    # rate_limit_chat implies get_current_active_user and returns the same
    # user, so depending on it is what applies the daily quota (429). Taking
    # the caller from it rather than from get_current_active_user is what
    # makes the limit impossible to wire up and leave off.
    current_user: User = Depends(rate_limit_chat),
    db: Session = Depends(get_db),
) -> AgentChatResponse:
    """
    Ask the agent a question and get an answer grounded in its knowledge base.

    Writes two AgentMessage rows (the question and the answer) and one
    AuditLog entry. Omit `conversation_id` to start a thread; send it back to
    ask a follow-up that sees what came before.
    """
    return agent_service.chat(db, current_user, domain_id, data)


# Not require_role(UserRole.USER): an ADMIN has to be able to open a
# conversation the audit trail points at. Owner-or-ADMIN, and the domain's own
# visibility, are decided in the service — see agent_service.get_conversation().
@router.get(
    "/{domain_id}/conversations/{conversation_id}",
    response_model=AgentConversationResponse,
)
def get_conversation(
    domain_id: str,
    conversation_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AgentConversationResponse:
    """Return one conversation's messages in chronological order."""
    return agent_service.get_conversation(db, current_user, domain_id, conversation_id)
