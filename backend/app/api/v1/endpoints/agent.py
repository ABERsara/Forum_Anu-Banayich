"""
AI agent endpoints.

GET    /agents                                            – list the agent domains
                                                            visible to the current user
POST   /agents/{domain_id}/knowledge-entries              – add knowledge base content
PATCH  /agents/{domain_id}/knowledge-entries/{entry_id}   – edit it
DELETE /agents/{domain_id}/knowledge-entries/{entry_id}   – remove it

The three knowledge base routes are for the people who maintain a domain, not
for the members who ask it questions, and each one refuses in three stages:
the role (a member never reaches the database at all), then the domain (404 if
it does not exist), then the discipline (403 if it is not theirs).

Those three refusals are all these handlers do. The writes themselves, and the
decision of when an edit is worth re-indexing, live in agent_service — so a
later ticket that needs to create an entry outside of HTTP calls the same code
rather than a copy of it.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.constants import UserRole
from app.core.dependencies import get_current_active_user, get_db, require_role
from app.models.user import User
from app.schemas.agent import (
    AgentDomainResponse,
    AgentKnowledgeEntryCreate,
    AgentKnowledgeEntryResponse,
    AgentKnowledgeEntryUpdate,
)
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["AI Agent"])

# Who may maintain a knowledge base at all. Which domains each of them may
# maintain is agent_service.can_manage_knowledge()'s question; this only keeps
# an ordinary member from reaching it.
_knowledge_manager = require_role(UserRole.ADMIN, UserRole.PROFESSIONAL)


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


@router.post(
    "/{domain_id}/knowledge-entries",
    response_model=AgentKnowledgeEntryResponse,
    status_code=201,
    dependencies=[Depends(_knowledge_manager)],
)
def create_knowledge_entry(
    domain_id: str,
    data: AgentKnowledgeEntryCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AgentKnowledgeEntryResponse:
    """Add an entry to a domain's knowledge base and index it for retrieval."""
    agent_service.get_manageable_domain(db, domain_id, current_user)
    entry = agent_service.create_knowledge_entry(db, domain_id, data, current_user)
    return AgentKnowledgeEntryResponse.model_validate(entry)


@router.patch(
    "/{domain_id}/knowledge-entries/{entry_id}",
    response_model=AgentKnowledgeEntryResponse,
    dependencies=[Depends(_knowledge_manager)],
)
def update_knowledge_entry(
    domain_id: str,
    entry_id: str,
    data: AgentKnowledgeEntryUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AgentKnowledgeEntryResponse:
    """Edit a knowledge base entry, re-indexing it only if its content changed."""
    agent_service.get_manageable_domain(db, domain_id, current_user)
    entry = agent_service.get_entry_or_404(db, domain_id, entry_id)
    entry = agent_service.update_knowledge_entry(db, entry, data, current_user)
    return AgentKnowledgeEntryResponse.model_validate(entry)


@router.delete(
    "/{domain_id}/knowledge-entries/{entry_id}",
    status_code=204,
    dependencies=[Depends(_knowledge_manager)],
)
def delete_knowledge_entry(
    domain_id: str,
    entry_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Response:
    """Remove a knowledge base entry; its chunks go with it."""
    agent_service.get_manageable_domain(db, domain_id, current_user)
    entry = agent_service.get_entry_or_404(db, domain_id, entry_id)
    agent_service.delete_knowledge_entry(db, entry)
    return Response(status_code=204)
