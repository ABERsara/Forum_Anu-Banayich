"""
FastAPI dependency functions.

These are injected into endpoints using `Depends(...)`.

Examples
--------
@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.get("/admin/stuff")
def admin_only(current_user: User = Depends(require_role(UserRole.ADMIN))):
    ...
"""

from collections.abc import Callable, Generator
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import UserRole
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.services import agent_service
from app.services.user_service import ensure_account_active, get_user_by_id

if TYPE_CHECKING:
    from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")


def get_db() -> Generator[Session, None, None]:
    """Yields a DB session, then closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> "User":
    """
    Decode JWT and load the corresponding user from DB.

    Does NOT enforce account_status — use get_current_active_user (or check
    the status yourself) if the endpoint requires an active account.

    Raises 401 if the token is invalid or the user is not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="לא ניתן לאמת את הזהות. יש להתחבר מחדש.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_access_token(token)
    except JWTError:
        raise credentials_exception from None

    user = get_user_by_id(db, user_id)
    if user is None:
        raise credentials_exception

    return user


def get_current_active_user(current_user: "User" = Depends(get_current_user)) -> "User":
    """Use when the endpoint requires a logged-in user with an ACTIVE account."""
    ensure_account_active(current_user)
    return current_user


def require_role(*roles: UserRole) -> Callable[..., "User"]:
    """
    Returns a dependency that enforces one of the given roles (implies active account).

    Usage:
        @router.get("/admin/...")
        def admin_endpoint(user = Depends(require_role(UserRole.ADMIN))):
            ...
    """

    def _check(current_user: "User" = Depends(get_current_active_user)) -> "User":
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="אין לך הרשאה לבצע פעולה זו.",
            )
        return current_user

    return _check


def rate_limit_chat(
    current_user: "User" = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> "User":
    """
    Enforce settings.AGENT_RATE_LIMIT_PER_DAY on the AI agent chat, and return
    the caller.

    A dependency rather than a check inside the endpoint, and one that returns
    the caller: the chat endpoint depends on this *instead of* on
    get_current_active_user, so there is no way to wire the endpoint up and
    leave the limit off. It runs before the endpoint body does, which is what
    keeps an over-quota request from reaching retrieval or the provider.

    The window is rolling — see agent_service.messages_left_today().

    Usage:
        @router.post("/agents/{domain_id}/chat")
        def chat(user = Depends(rate_limit_chat)):
            ...
    """
    if agent_service.messages_left_today(db, current_user) <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"הגעת למכסת {settings.AGENT_RATE_LIMIT_PER_DAY} ההודעות היומית "
                "לסוכן. אפשר לנסות שוב מאוחר יותר, או לפנות לייעוץ מקצועי אנושי "
                "דרך מודול הייעוץ באתר."
            ),
        )
    return current_user
