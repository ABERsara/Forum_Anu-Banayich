"""
FastAPI dependency functions.

These are injected into endpoints using `Depends(...)`.

Examples
--------
@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.get("/admin/stuff")
def admin_only(current_user: User = Depends(require_admin)):
    ...
"""

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AccountStatus, UserRole
from app.core.security import ALGORITHM
from app.db.session import SessionLocal

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
):
    """
    Decode JWT, load user from DB.

    Raises 401 if the token is invalid or the user is not found.
    """
    # Import here to avoid circular imports
    from app.models.user import User  # noqa: PLC0415

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="לא ניתן לאמת את הזהות. יש להתחבר מחדש.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    if user.account_status not in (AccountStatus.ACTIVE,):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="החשבון אינו פעיל.",
        )

    return user


def get_current_active_user(current_user=Depends(get_current_user)):
    """Alias – use when you just need any logged-in, active user."""
    return current_user


def require_role(*roles: UserRole):
    """
    Returns a dependency that enforces one of the given roles.

    Usage:
        @router.get("/admin/...")
        def admin_endpoint(user = Depends(require_role(UserRole.ADMIN))):
            ...
    """
    def _check(current_user=Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="אין לך הרשאה לבצע פעולה זו.",
            )
        return current_user

    return _check


def require_admin(current_user=Depends(get_current_user)):
    return require_role(UserRole.ADMIN)(current_user)


def require_moderator(current_user=Depends(get_current_user)):
    return require_role(UserRole.MODERATOR, UserRole.ADMIN)(current_user)


def require_professional(current_user=Depends(get_current_user)):
    return require_role(UserRole.PROFESSIONAL)(current_user)
