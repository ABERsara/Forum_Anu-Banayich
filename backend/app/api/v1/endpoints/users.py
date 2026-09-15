"""
User profile endpoints.

GET  /users/me                    – current user's profile
PUT  /users/me                    – update own profile
DELETE /users/me                  – delete own account (GDPR)
GET  /users/me/messages/export    – export own private messages (GDPR, ABF-117)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import AuditAction, UserRole
from app.core.dependencies import get_current_active_user, get_db
from app.core.i18n import translate
from app.models.user import User
from app.schemas.forum import DirectMessageExportItem, DirectMessageExportResponse
from app.schemas.user import UserProfile
from app.services import retention_service, user_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserProfile)
def get_my_profile(current_user: User = Depends(get_current_active_user)) -> User:
    """Return the currently authenticated user's profile."""
    return current_user


@router.delete("/me", status_code=204)
def delete_my_account(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    GDPR right-to-be-forgotten – delete own account.

    Personal data is scrubbed and the account is deactivated; private
    messages are deleted outright (spec §9.4 — unlike a forum post, which is
    only anonymised, out of scope for this endpoint). See
    user_service.delete_own_account() for what "deleted" means here and why.

    Immediate — no OTP step, no admin-approval queue.
    """
    user_service.delete_own_account(db, current_user)


@router.get("/me/messages/export", response_model=DirectMessageExportResponse)
def export_my_messages(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> DirectMessageExportResponse:
    """
    Export every private message the caller sent or received (spec §9.5).

    §3.2's permission table grants this to the plain USER role only — a
    moderator/admin/professional account has no personal "cell"
    correspondence to export in the GDPR sense this endpoint serves.
    """
    if current_user.role != UserRole.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=translate("errors.forbidden"),
        )

    messages = retention_service.export_user_direct_messages(db, current_user)
    items = [DirectMessageExportItem(**message) for message in messages]

    log_action(
        db,
        actor=current_user,
        action=AuditAction.DATA_EXPORTED,
        entity_type="User",
        entity_id=current_user.id,
        details={"exported_message_count": len(items)},
    )

    return DirectMessageExportResponse(items=items, total=len(items))
