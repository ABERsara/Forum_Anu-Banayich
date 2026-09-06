"""
AI agent service.

get_visible_domains() applies the same group/sector visibility filter as the
forum (see forum_service._content_filter): a domain is visible to a user when
its group_visibility matches the user's group or is "all", AND its
sector_visibility matches the user's sector or is "all". Inactive domains are
never returned.
"""

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.constants import GroupVisibility, SectorVisibility
from app.models.agent import AgentDomain
from app.models.user import User


def get_visible_domains(db: Session, user: User) -> list[AgentDomain]:
    """
    Return the active agent domains this user may see, ordered by lower(name)
    then id — deterministic, and case-insensitive for Latin names. Hebrew
    ordering still depends on the DB collation (SQLite compares code points,
    Postgres uses its locale), which is cosmetic here: the catalog is a
    handful of domains.

    Visibility rule (DB-side, mirrors forum_service._content_filter):
        (group_visibility == user's group  OR  group_visibility == ALL)
        AND
        (sector_visibility == user's sector  OR  sector_visibility == ALL)

    user_type/sector are Optional on User (other roles don't have them). The
    only caller, GET /agents, is gated by require_role(UserRole.USER), so they
    are always set here; check it rather than let a non-USER caller hit a
    confusing AttributeError inside the filter.
    """
    if user.user_type is None:
        raise ValueError("get_visible_domains() requires a user with user_type set")
    if user.sector is None:
        raise ValueError("get_visible_domains() requires a user with sector set")
    group_visibility = GroupVisibility(user.user_type.value)
    sector_visibility = SectorVisibility(user.sector.value)
    return (
        db.query(AgentDomain)
        .filter(
            AgentDomain.is_active.is_(True),
            or_(
                AgentDomain.group_visibility == group_visibility,
                AgentDomain.group_visibility == GroupVisibility.ALL,
            ),
            or_(
                AgentDomain.sector_visibility == sector_visibility,
                AgentDomain.sector_visibility == SectorVisibility.ALL,
            ),
        )
        .order_by(func.lower(AgentDomain.name), AgentDomain.id)
        .all()
    )
