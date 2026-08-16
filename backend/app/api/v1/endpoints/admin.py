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

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import UserRole
from app.core.dependencies import get_current_active_user, get_db, require_role
from app.models.user import User
from app.schemas.user import (
    ProfessionalUpdateRequest,
    RegistrationDetailView,
    RegistrationRejectRequest,
    SuspendUserRequest,
    UserAdminView,
    UserProfile,
)
from app.services import user_service

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


@router.get("/registrations", response_model=list[UserAdminView])
def list_pending_registrations(
    db: Session = Depends(get_db),
) -> list[UserAdminView]:
    """
    Return all registrations awaiting admin approval.
    """
    return [
        UserAdminView.model_validate(user)
        for user in user_service.get_pending_registrations(db)
    ]


@router.get("/registrations/{user_id}", response_model=RegistrationDetailView)
def get_registration(
    user_id: str, db: Session = Depends(get_db)
) -> RegistrationDetailView:
    """
    Return a single registration awaiting approval, with the documents filed
    with it — the full applicant profile plus document metadata.

    404 when there is no such user, 403 once the registration is no longer
    waiting for a decision.

    The documents are metadata only. The presigned URLs that open the files
    themselves (SPEC §9.1) are not built yet, so nothing here is a link.
    """
    return RegistrationDetailView.model_validate(
        user_service.get_registration(db, user_id)
    )


@router.post("/registrations/{user_id}/approve", response_model=UserAdminView)
def approve_registration(
    user_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> UserAdminView:
    """
    Approve a pending registration.
    """
    user = user_service.approve_registration(db, user_id, current_user)
    return UserAdminView.model_validate(user)


@router.post("/registrations/{user_id}/reject", response_model=UserAdminView)
def reject_registration(
    user_id: str,
    data: RegistrationRejectRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> UserAdminView:
    """
    Reject a pending registration with a reason.
    """
    user = user_service.reject_registration(db, user_id, current_user, data.reason)
    return UserAdminView.model_validate(user)


@router.get("/users/active", response_model=list[UserAdminView])
def list_active_users(db: Session = Depends(get_db)) -> list[UserAdminView]:
    """
    Return all active users.
    """
    return [
        UserAdminView.model_validate(user) for user in user_service.get_active_users(db)
    ]


@router.get("/professionals", response_model=list[UserProfile])
def list_professionals(db: Session = Depends(get_db)) -> list[UserProfile]:
    """Return all professional users."""
    # TODO: query users where role=PROFESSIONAL
    return []


@router.put("/professionals/{user_id}")
def update_professional(
    user_id: str,
    data: ProfessionalUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """Update a professional's profile (domain, sectors, groups, description)."""
    # TODO: implement + audit log
    raise NotImplementedError


@router.post("/users/{user_id}/suspend", response_model=UserAdminView)
def suspend_user(
    user_id: str,
    data: SuspendUserRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> UserAdminView:
    """
    Manually suspend a user.
    """
    user = user_service.suspend_user(db, user_id, current_user, data.hours, data.reason)
    return UserAdminView.model_validate(user)


@router.get("/audit-log")
def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=100),
    db: Session = Depends(get_db),
) -> list[Any]:
    """
    Return paginated audit log (admin only).

    TODO: call audit_service.get_audit_log(db, page, page_size)
    """
    # TODO: implement
    return []
