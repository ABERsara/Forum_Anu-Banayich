from datetime import UTC, datetime, timedelta
from typing import cast

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return cast(
        str,
        jwt.encode(
            {"exp": expire, "sub": subject},
            settings.SECRET_KEY,
            algorithm=ALGORITHM,
        ),
    )


def verify_password(plain: str, hashed: str) -> bool:
    return cast(bool, pwd_context.verify(plain, hashed))


def get_password_hash(password: str) -> str:
    return cast(str, pwd_context.hash(password))
