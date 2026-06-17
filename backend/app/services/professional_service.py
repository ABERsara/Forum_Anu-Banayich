"""
Professional advisory service.

Handles professional queries (questions and answers).

TODO list for junior developer:
  [ ] implement create_query()
  [ ] implement answer_query()
  [ ] implement get_public_qa()
  [ ] implement get_my_questions() (for the asker)
  [ ] implement get_pending_questions() (for the professional)
"""

from sqlalchemy.orm import Session

from app.core.constants import QueryStatus
from app.models.professional import ProfessionalQuery
from app.models.user import User
from app.schemas.professional import (
    ProfessionalAnswerRequest,
    ProfessionalQueryCreate,
    ProfessionalQueryResponse,
    PublicQAResponse,
)
from app.services.email_service import send_question_notification


def _build_alias(user: User) -> str:
    """
    Build the alias shown to the professional for a private query.
    Example: "אלמנה – ספרדי"
    """
    from app.core.constants import SECTOR_LABELS, USER_TYPE_LABELS  # noqa: PLC0415
    user_type_label = USER_TYPE_LABELS.get(user.user_type, "")  # type: ignore[arg-type]
    sector_label = SECTOR_LABELS.get(user.sector, "")  # type: ignore[arg-type]
    return f"{user_type_label} – {sector_label}"


def create_query(db: Session, data: ProfessionalQueryCreate, asker: User) -> ProfessionalQuery:
    """
    Ask a professional question.

    TODO:
      1. Validate: either professional_id OR domain must be set (not both None)
      2. If professional_id given: verify that professional serves asker's group/sector
      3. Create ProfessionalQuery object, save to DB
      4. Send email notification:
           - specific professional  → direct email
           - general domain question → email to all matching professionals
      5. Return the query
    """
    # TODO: implement this function
    raise NotImplementedError("create_query() is not yet implemented")


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


def get_my_questions(db: Session, asker: User) -> list[ProfessionalQuery]:
    """
    Return all questions asked by the current user (both public and private).

    TODO:
      Query where asker_id == asker.id, order by created_at DESC
    """
    # TODO: implement this function
    raise NotImplementedError("get_my_questions() is not yet implemented")


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
