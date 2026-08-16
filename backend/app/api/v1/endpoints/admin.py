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
GET    /admin/moderators             – the moderator roster
POST   /admin/moderators             – appoint a moderator
PATCH  /admin/moderators/{id}        – update a moderator's cells / alert email
DELETE /admin/moderators/{id}        – remove a moderator from the roster
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
    ModeratorAdminView,
    ModeratorCreateRequest,
    ModeratorUpdateRequest,
    ProfessionalUpdateRequest,
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


@router.get("/registrations/{user_id}", response_model=UserAdminView)
def get_registration(user_id: str, db: Session = Depends(get_db)) -> UserAdminView:
    """
    Return a single registration with all uploaded documents.

    TODO: load user + documents, build response with presigned URLs for documents
    """
    # TODO: implement
    raise NotImplementedError


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


@router.get("/moderators", response_model=list[ModeratorAdminView])
def list_moderators(db: Session = Depends(get_db)) -> list[ModeratorAdminView]:
    """Return the moderator roster with the cells assigned to each moderator."""
    return [
        ModeratorAdminView.model_validate(moderator)
        for moderator in user_service.get_moderators(db)
    ]


@router.post("/moderators", response_model=ModeratorAdminView, status_code=201)
def add_moderator(
    data: ModeratorCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ModeratorAdminView:
    """Appoint a moderator over the given cells."""
    moderator = user_service.create_moderator(db, data, current_user)
    return ModeratorAdminView.model_validate(moderator)


@router.patch("/moderators/{user_id}", response_model=ModeratorAdminView)
def update_moderator(
    user_id: str,
    data: ModeratorUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ModeratorAdminView:
    """Update a moderator's assigned cells and/or their alert email."""
    moderator = user_service.update_moderator(db, user_id, data, current_user)
    return ModeratorAdminView.model_validate(moderator)


@router.delete("/moderators/{user_id}", status_code=204)
def remove_moderator(
    user_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Remove a moderator from the roster.

    204, no body: the roster no longer holds this moderator, so there is
    nothing about them left for the client to render.
    """
    user_service.remove_moderator(db, user_id, current_user)


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
