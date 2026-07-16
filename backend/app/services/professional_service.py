"""
Professional advisory service.

Handles professional queries (questions and answers).

TODO list for junior developer:
  [x] implement create_query()
  [ ] implement answer_query()
  [ ] implement get_public_qa()
  [x] implement get_my_questions() (for the asker)
  [ ] implement get_pending_questions() (for the professional)
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.constants import ProfessionalDomain, UserRole
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
    from app.core.constants import SECTOR_LABELS, USER_TYPE_LABELS  # noqa: PLC0415

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
) -> ProfessionalQuery:
    """
    Professional submits an answer.

    TODO:
      1. Load query, verify professional_id matches or domain matches
      2. Set answer, answered_at, status = ANSWERED
      3. Save to DB
      4. Notify the asker (push notification / email)
      5. Return the updated query
    """
    # TODO: implement this function
    raise NotImplementedError("answer_query() is not yet implemented")


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


def get_pending_questions(db: Session, professional: User) -> list[ProfessionalQuery]:
    """
    Return questions waiting for this professional's answer.

    TODO:
      1. Find questions where (professional_id == professional.id)
         OR (domain == professional.professional_domain AND professional_id IS NULL)
      2. Filter status == OPEN
      3. Verify the asker's group/sector is in the professional's assigned groups/sectors
    """
    # TODO: implement this function
    raise NotImplementedError("get_pending_questions() is not yet implemented")
