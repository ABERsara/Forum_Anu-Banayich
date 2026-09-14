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
"""

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.constants import UserRole
from app.core.dependencies import get_current_active_user, get_db, require_role
from app.models.agent import AgentKnowledgeEntry
from app.models.user import User
from app.schemas.agent import (
    AgentDomainResponse,
    AgentKnowledgeEntryCreate,
    AgentKnowledgeEntryResponse,
    AgentKnowledgeEntryUpdate,
)
from app.services import agent_service, rag_service

logger = logging.getLogger(__name__)

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


def _index(db: Session, entry: AgentKnowledgeEntry) -> None:
    """Re-index one entry, without letting a failed index fail the write.

    The entry is already committed by the time this runs, and it is the
    professional's work. Reporting a 500 for it because Google was unreachable
    would be the worse outcome by far — the write did happen, and the caller
    would be told it did not. An unindexed entry is saved, visible and editable,
    and the next PATCH that touches its content indexes it. So this logs and
    returns.

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

    entry = AgentKnowledgeEntry(
        domain_id=domain_id,
        updated_by=current_user.id,
        **data.model_dump(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # After the commit, never inside it — index_entry() makes an HTTP call.
    _index(db, entry)
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

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(entry, field, value)
    entry.updated_by = current_user.id
    db.commit()
    db.refresh(entry)

    # Only the two fields an embedding is built from. index_entry() embeds each
    # chunk with the title in front of it, so a title left unindexed would go on
    # being searched for under the old one — which is worse than not indexing it
    # at all. A source_name or source_url fix changes nothing an embedding sees,
    # and must not spend a paid round trip rebuilding identical vectors.
    if changes.keys() & {"content", "title"}:
        _index(db, entry)
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

    # The chunks are deleted by the relationship's delete-orphan cascade, so
    # nothing is left behind to be retrieved and quoted after the entry that
    # said it is gone.
    db.delete(entry)
    db.commit()
    return Response(status_code=204)
