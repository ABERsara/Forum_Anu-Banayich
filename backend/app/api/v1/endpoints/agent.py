"""
AI agent endpoints.

GET /agents – list the agent domains visible to the current user
              (group/sector filtered catalog).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.constants import UserRole
from app.core.dependencies import get_current_active_user, get_db, require_role
from app.models.user import User
from app.schemas.agent import AgentDomainResponse
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
