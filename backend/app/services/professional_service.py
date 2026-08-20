"""
Professional advisory service.

Handles professional queries (questions and answers).

TODO list for junior developer:
  [x] implement create_query()
  [x] implement answer_query()
  [ ] implement get_public_qa()
  [x] implement get_my_questions() (for the asker)
  [x] implement get_pending_questions() (for the professional)
"""

import enum
from datetime import UTC, datetime
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Query, Session, contains_eager, joinedload

from app.core.constants import (
    SECTOR_LABELS,
    USER_TYPE_LABELS,
    ProfessionalDomain,
    QueryStatus,
    Sector,
    UserRole,
    UserType,
)
from app.models.professional import ProfessionalQuery
from app.models.user import User
from app.schemas.professional import (
    ProfessionalAnswerRequest,
    ProfessionalQueryCreate,
    ProfessionalQueryResponse,
    PublicQAResponse,
)
from app.schemas.user import ProfessionalProfile, UserPublic
from app.services import email_service


def _build_alias(user: User) -> str:
    """
    Build the alias shown to the professional for a private query.
    Example: "אלמנה – ספרדי"
    """
    user_type_label = USER_TYPE_LABELS.get(user.user_type, "")  # type: ignore[arg-type]
    sector_label = SECTOR_LABELS.get(user.sector, "")  # type: ignore[arg-type]
    return f"{user_type_label} – {sector_label}"


def _professional_matches_asker(professional: User, asker: User) -> bool:
    """
    True if `professional` serves the asker's group (user_type) and sector.

    professional_groups/professional_sectors are JSON lists of UserType/Sector
    values, or ["all"].
    """
    groups = professional.professional_groups or []
    sectors = professional.professional_sectors or []
    group_ok = "all" in groups or (
        asker.user_type is not None and asker.user_type.value in groups
    )
    sector_ok = "all" in sectors or (
        asker.sector is not None and asker.sector.value in sectors
    )
    return group_ok and sector_ok


_EnumT = TypeVar("_EnumT", bound=enum.Enum)


def _assigned_members(
    assigned: list[str] | None, enum_cls: type[_EnumT]
) -> list[_EnumT] | None:
    """
    Translate one of the professional_groups/professional_sectors JSON lists
    into enum members that can be bound into a SQL query.

    Returns None for ["all"] – meaning "no restriction, skip the filter".
    Unknown strings are dropped, so a professional assigned to nothing (or to
    values that no longer exist) matches no asker at all, exactly like
    _professional_matches_asker() decides for a single row.
    """
    values = assigned or []
    if "all" in values:
        return None
    return [member for member in enum_cls if member.value in values]


def _restrict_to_assigned_askers(
    query: Query[ProfessionalQuery], professional: User
) -> Query[ProfessionalQuery]:
    """
    Keep only queries whose asker belongs to a group AND sector this
    professional was assigned to serve.

    SQL-side twin of _professional_matches_asker(): same rule, evaluated by the
    database instead of over rows already fetched – private questions must never
    leave the DB for a professional who may not read them (see the content
    filter rule in CONTRIBUTING.md). Keep the two in sync.

    The caller must already have joined ProfessionalQuery.asker, so that `User`
    here refers to the asker and not to the professional the query points at.
    """
    groups = _assigned_members(professional.professional_groups, UserType)
    sectors = _assigned_members(professional.professional_sectors, Sector)

    if groups is not None:
        query = query.filter(User.user_type.in_(groups))
    if sectors is not None:
        query = query.filter(User.sector.in_(sectors))
    return query


def _professional_may_answer(query: ProfessionalQuery, professional: User) -> bool:
    """
    True if `professional` is allowed to answer `query` – the same targeting
    rule get_pending_questions() lists by:
      - a question addressed to them personally, or
      - a general question in their domain, from an asker they serve.
    """
    if query.professional_id is not None:
        return query.professional_id == professional.id

    return (
        professional.professional_domain is not None
        and query.domain == professional.professional_domain
        and _professional_matches_asker(professional, query.asker)
    )


def _to_response(query: ProfessionalQuery) -> ProfessionalQueryResponse:
    """
    Build the client-facing response for a query, enforcing the privacy rule:
    the asker's real identity is only included if they chose to reveal it.
    """
    return ProfessionalQueryResponse(
        id=query.id,
        content=query.content,
        answer=query.answer,
        is_public=query.is_public,
        status=query.status,
        is_featured=query.is_featured,
        domain=query.domain,
        professional=ProfessionalProfile.model_validate(query.professional)
        if query.professional is not None
        else None,
        asker_alias=_build_alias(query.asker),
        asker=UserPublic.model_validate(query.asker) if query.show_real_name else None,
        created_at=query.created_at,
        answered_at=query.answered_at,
    )


def _notify_professionals(
    db: Session,
    professional: User | None,
    domain: ProfessionalDomain | None,
    asker: User,
    query_id: str,
) -> None:
    """
    Send the new-question email notification(s):
      - specific professional  → direct email
      - general domain question → email to all matching professionals
    """
    if professional is not None:
        email_service.send_direct_question_notification(professional.email, query_id)
        return

    if domain is None:
        return

    matching_professionals = (
        db.query(User)
        .filter(
            User.role == UserRole.PROFESSIONAL,
            User.professional_domain == domain,
            User.is_active_professional.is_(True),
        )
        .all()
    )
    for candidate in matching_professionals:
        if _professional_matches_asker(candidate, asker):
            email_service.send_domain_question_notification(candidate.email, query_id)


def create_query(
    db: Session, data: ProfessionalQueryCreate, asker: User
) -> ProfessionalQueryResponse:
    """
    Ask a professional question.

    1. Validate: either professional_id OR domain must be set (not both None)
    2. If professional_id given: verify that professional serves asker's group/sector
    3. Create ProfessionalQuery object, save to DB
    4. Send email notification (see _notify_professionals)
    5. Return the query
    """
    if data.professional_id is None and data.domain is None:
        raise HTTPException(
            status_code=400,
            detail="Either professional_id or domain must be provided",
        )

    professional: User | None = None
    if data.professional_id is not None:
        professional = (
            db.query(User)
            .filter(User.id == data.professional_id, User.role == UserRole.PROFESSIONAL)
            .first()
        )
        if professional is None or not professional.is_active_professional:
            raise HTTPException(status_code=404, detail="Professional not found")
        if not _professional_matches_asker(professional, asker):
            raise HTTPException(
                status_code=403,
                detail="This professional does not serve your group/sector",
            )

    query = ProfessionalQuery(
        asker_id=asker.id,
        professional_id=data.professional_id,
        domain=data.domain,
        content=data.content,
        is_public=data.is_public,
        show_real_name=data.show_real_name,
    )
    db.add(query)
    db.commit()
    db.refresh(query)
    # professional/asker are already loaded in this scope — assign them directly
    # instead of letting _to_response() trigger a lazy-load SELECT for each.
    query.professional = professional
    query.asker = asker

    _notify_professionals(db, professional, data.domain, asker, query.id)

    return _to_response(query)


def answer_query(
    db: Session,
    query_id: str,
    data: ProfessionalAnswerRequest,
    professional: User,
) -> ProfessionalQueryResponse:
    """
    Professional submits an answer: stores it, closes the question and emails
    the asker.

    Permission: see _professional_may_answer().

    Answering is a one-way transition. A general question reaches every
    professional in its domain, so two of them can hit this at the same time –
    the row lock plus the OPEN check make the first answer win, and the second
    gets 409 instead of silently overwriting it. Editing an existing answer is
    a separate feature (sprint 5).
    """
    query = (
        db.query(ProfessionalQuery)
        .options(
            joinedload(ProfessionalQuery.asker),
            joinedload(ProfessionalQuery.professional),
        )
        # Row-level lock against the concurrent-answer race described above.
        # Scoped with of= so the JOINed users rows are not locked too.
        # No-op on SQLite (dev), enforced on PostgreSQL (production).
        .with_for_update(of=ProfessionalQuery)
        .filter(ProfessionalQuery.id == query_id)
        .first()
    )
    if query is None:
        raise HTTPException(status_code=404, detail="השאלה לא נמצאה.")

    if not _professional_may_answer(query, professional):
        raise HTTPException(status_code=403, detail="אין לך הרשאה לענות על שאלה זו.")

    if query.status != QueryStatus.OPEN:
        raise HTTPException(status_code=409, detail="השאלה כבר נענתה.")

    query.answer = data.answer
    query.status = QueryStatus.ANSWERED
    # answered_at is a naive DateTime column, like created_at – store UTC
    # without the tzinfo so the two stay comparable (as in user_service).
    query.answered_at = datetime.now(UTC).replace(tzinfo=None)

    # Read both while the instance is still loaded: commit() expires it, and
    # touching asker/professional afterwards would re-SELECT them one lazy
    # load at a time (the same concern create_query() notes).
    response = _to_response(query)
    asker_email = query.asker.email

    db.commit()

    # Only after the answer is safely stored: a failed notification must never
    # roll back an answer the professional already submitted.
    email_service.send_answer_notification(asker_email, query_id)

    return response


def get_public_qa(
    db: Session,
    current_user: User,
    domain: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> list[PublicQAResponse]:
    """
    Return public answered questions visible to the current user.

    Visibility: same as forum posts – group+sector filter applies.

    TODO:
      1. Query ProfessionalQuery where is_public=True AND status=ANSWERED
      2. Apply group+sector filter based on the asker's profile
      3. Optionally filter by domain
      4. Return paginated list
    """
    # TODO: implement this function
    raise NotImplementedError("get_public_qa() is not yet implemented")


def get_my_questions(db: Session, asker: User) -> list[ProfessionalQueryResponse]:
    """
    Return all questions asked by the current user (both public and private),
    ordered by created_at DESC.
    """
    queries = (
        db.query(ProfessionalQuery)
        .options(
            joinedload(ProfessionalQuery.professional),
            joinedload(ProfessionalQuery.asker),
        )
        .filter(ProfessionalQuery.asker_id == asker.id)
        .order_by(ProfessionalQuery.created_at.desc())
        .all()
    )
    return [_to_response(query) for query in queries]


def get_pending_questions(
    db: Session, professional: User
) -> list[ProfessionalQueryResponse]:
    """
    Return the questions still waiting for this professional's answer.

    A question is pending for them when it is still OPEN, it targets them
    (personally, or through their domain when no professional was chosen), and
    the asker belongs to a group+sector they were assigned to serve.

    Oldest first: this is a work queue, so whoever has been waiting longest
    comes first – unlike get_my_questions(), which is a personal history and
    shows the newest question on top.
    """
    targets = [ProfessionalQuery.professional_id == professional.id]
    if professional.professional_domain is not None:
        # A general question fans out to one domain only; a professional
        # without a domain can never be its target.
        targets.append(
            and_(
                ProfessionalQuery.professional_id.is_(None),
                ProfessionalQuery.domain == professional.professional_domain,
            )
        )

    query = (
        db.query(ProfessionalQuery)
        # join + contains_eager: a single SELECT that both filters on the
        # asker's group/sector and loads the asker _to_response() needs for
        # the alias – rather than a filtering join plus a second fetch.
        .join(ProfessionalQuery.asker)
        .options(
            contains_eager(ProfessionalQuery.asker),
            joinedload(ProfessionalQuery.professional),
        )
        .filter(ProfessionalQuery.status == QueryStatus.OPEN, or_(*targets))
    )

    queries = (
        _restrict_to_assigned_askers(query, professional)
        .order_by(ProfessionalQuery.created_at.asc())
        .all()
    )
    return [_to_response(query) for query in queries]
