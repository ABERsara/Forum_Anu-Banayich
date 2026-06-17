"""
Admin endpoints.

All routes require UserRole.ADMIN.

GET  /admin/registrations            – pending registrations queue
GET  /admin/registrations/{id}       – single registration with documents
POST /admin/registrations/{id}/approve – approve a registration
POST /admin/registrations/{id}/reject  – reject a registration
GET  /admin/professionals            – all professionals
POST /admin/professionals            – add a professional
PUT  /admin/professionals/{id}       – update professional profile
GET  /admin/audit-log                – full audit log
POST /admin/users/{id}/suspend       – suspend a user manually
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import UserRole
from app.core.dependencies import get_current_user, get_db, require_role
from app.models.user import User
from app.schemas.user import (
    ProfessionalUpdateRequest,
    RegistrationRejectRequest,
    SuspendUserRequest,
    UserAdminView,
    UserProfile,
)
from app.services import audit_service, user_service

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


@router.get("/registrations", response_model=list[UserAdminView])
def list_pending_registrations(
    db: Session = Depends(get_db),
):
    """
    Return all registrations awaiting admin approval.

    TODO: call user_service.get_pending_registrations(db)
    """
    # TODO: implement
    return []


@router.get("/registrations/{user_id}", response_model=UserAdminView)
def get_registration(user_id: str, db: Session = Depends(get_db)):
    """
    Return a single registration with all uploaded documents.

    TODO: load user + documents, build response with presigned URLs for documents
    """
    # TODO: implement
    raise NotImplementedError


@router.post("/registrations/{user_id}/approve")
def approve_registration(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Approve a pending registration.

    TODO: call user_service.approve_registration(db, user_id, current_user)
    """
    # TODO: implement
    raise NotImplementedError


@router.post("/registrations/{user_id}/reject")
def reject_registration(
    user_id: str,
    data: RegistrationRejectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Reject a pending registration with a reason.

    TODO: call user_service.reject_registration(db, user_id, current_user, data.reason)
    """
    # TODO: implement
    raise NotImplementedError


@router.get("/professionals", response_model=list[UserProfile])
def list_professionals(db: Session = Depends(get_db)):
    """Return all professional users."""
    # TODO: query users where role=PROFESSIONAL
    return []


@router.put("/professionals/{user_id}")
def update_professional(
    user_id: str,
    data: ProfessionalUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a professional's profile (domain, sectors, groups, description)."""
    # TODO: implement + audit log
    raise NotImplementedError


@router.post("/users/{user_id}/suspend")
def suspend_user(
    user_id: str,
    data: SuspendUserRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually suspend a user.

    TODO: call user_service.suspend_user(db, user_id, current_user, data.hours, data.reason)
    """
    # TODO: implement
    raise NotImplementedError


@router.get("/audit-log")
def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=100),
    db: Session = Depends(get_db),
):
    """
    Return paginated audit log (admin only).

    TODO: call audit_service.get_audit_log(db, page, page_size)
    """
    # TODO: implement
    return []
