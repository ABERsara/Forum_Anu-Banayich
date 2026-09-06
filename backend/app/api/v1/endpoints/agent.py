"""
AI agent endpoints.

POST /agents/{domain_id}/chat                    – ask the agent a question
GET  /agents/{domain_id}/conversations/{id}      – read a whole conversation

`domain_id` is an AgentDomain value, so an unknown agent is a 422 from the
path itself and never reaches a knowledge base.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.constants import AgentDomain
from app.core.dependencies import get_current_active_user, get_db, rate_limit_chat
from app.models.user import User
from app.schemas.agent import AgentChatRequest, AgentChatResponse, AgentConversationOut
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["AI Agent"])


@router.post("/{domain_id}/chat", response_model=AgentChatResponse, status_code=201)
def chat(
    domain_id: AgentDomain,
    data: AgentChatRequest,
    # rate_limit_chat implies get_current_active_user and returns the same
    # user, so depending on it is what applies the daily quota (429).
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


@router.get(
    "/{domain_id}/conversations/{conversation_id}",
    response_model=AgentConversationOut,
)
def get_conversation(
    domain_id: AgentDomain,
    conversation_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AgentConversationOut:
    """Return one conversation's messages in chronological order."""
    return agent_service.get_conversation(db, current_user, domain_id, conversation_id)
