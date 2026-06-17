"""
User profile endpoints.

GET  /users/me            – current user's profile
PUT  /users/me            – update own profile
DELETE /users/me          – delete own account (GDPR)
GET  /users/search        – search users for DM (same group only)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.user import UserProfile, UserPublic

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserProfile)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user


@router.get("/search", response_model=list[UserPublic])
def search_users(
    name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Search for users to send a direct message to.

    Only users in the same group are returned (no cross-group search).
    Returns name only – no phone, email or other PII.

    TODO: call forum_service.search_users_for_dm(db, current_user, name)
    """
    # TODO: implement
    return []


@router.delete("/me", status_code=204)
def delete_my_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    GDPR right-to-be-forgotten – delete own account.

    Personal data is deleted. Forum posts are anonymised (not deleted).
    Requires OTP confirmation (add that step to the frontend flow).

    TODO: implement deletion logic + audit log entry
    """
    # TODO: implement
    pass
