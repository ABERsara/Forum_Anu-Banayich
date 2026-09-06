"""
User profile endpoints.

GET  /users/me            – current user's profile
PUT  /users/me            – update own profile
DELETE /users/me          – delete own account (GDPR)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.user import UserProfile

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

    Personal data is deleted. Forum posts are anonymised (not deleted).
    Requires OTP confirmation (add that step to the frontend flow).

    TODO: implement deletion logic + audit log entry
    """
    # TODO: implement
    pass
