"""
AI agent service.

get_visible_domains() applies the same group/sector visibility filter as the
forum (see forum_service._content_filter): a domain is visible to a user when
its group_visibility matches the user's group or is "all", AND its
sector_visibility matches the user's sector or is "all". Inactive domains are
never returned.

The knowledge-base side below answers a different question. Reading the catalog
asks "which domains is this member offered"; editing a knowledge base asks "may
this professional edit this one", and the answer turns on their discipline, not
on their bereavement group — an admin and a professional have neither
user_type nor sector at all.
"""

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.constants import GroupVisibility, SectorVisibility, UserRole
from app.core.i18n import translate
from app.models.agent import AgentDomain, AgentKnowledgeEntry
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
