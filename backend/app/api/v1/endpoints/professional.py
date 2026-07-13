"""
Professional advisory endpoints.

GET  /advice/professionals       – list professionals visible to current user
GET  /advice/questions           – my questions
POST /advice/questions           – ask a question
GET  /advice/questions/public    – public answered Q&A feed
GET  /advice/questions/pending   – questions waiting for me (professional only)
PUT  /advice/questions/{id}/answer – submit answer (professional only)
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import ProfessionalDomain, UserRole
from app.core.dependencies import get_current_user, get_db, require_role
from app.models.user import User
from app.schemas.professional import (
    ProfessionalAnswerRequest,
    ProfessionalQueryCreate,
    ProfessionalQueryResponse,
    PublicQAResponse,
)
from app.schemas.user import ProfessionalProfile
from app.services import user_service

router = APIRouter(prefix="/advice", tags=["Professional Advisory"])


@router.get("/professionals", response_model=list[ProfessionalProfile])
def list_professionals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProfessionalProfile]:
    """
    List professionals visible to the current user (filtered by group+sector).
    """
    return [
        ProfessionalProfile.model_validate(pro)
        for pro in user_service.get_professionals_for_user(db, current_user)
    ]


@router.get("/questions", response_model=list[ProfessionalQueryResponse])
def my_questions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProfessionalQueryResponse]:
    """Return all questions asked by the current user."""
    # TODO: call professional_service.get_my_questions(db, current_user)
    return []


@router.post("/questions", response_model=ProfessionalQueryResponse, status_code=201)
def ask_question(
    data: ProfessionalQueryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfessionalQueryResponse:
    """
    Submit a professional question.

    TODO: call professional_service.create_query(db, data, current_user)
    """
    raise NotImplementedError


@router.get("/questions/public", response_model=list[PublicQAResponse])
def public_qa_feed(
    domain: ProfessionalDomain | None = Query(None),
    page: int = Query(1, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PublicQAResponse]:
    """
    Public Q&A knowledge base – answered questions visible to the user's group/sector.

    TODO: call professional_service.get_public_qa(db, current_user, domain, page)
    """
    return []


@router.get(
    "/questions/pending",
    response_model=list[ProfessionalQueryResponse],
    dependencies=[Depends(require_role(UserRole.PROFESSIONAL))],
)
def pending_questions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProfessionalQueryResponse]:
    """Questions waiting for the current professional to answer."""
    # TODO: call professional_service.get_pending_questions(db, current_user)
    return []


@router.put(
    "/questions/{query_id}/answer",
    response_model=ProfessionalQueryResponse,
    dependencies=[Depends(require_role(UserRole.PROFESSIONAL))],
)
def answer_question(
    query_id: str,
    data: ProfessionalAnswerRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfessionalQueryResponse:
    """Professional submits an answer to a question."""
    # TODO: call professional_service.answer_query(db, query_id, data, current_user)
    raise NotImplementedError
