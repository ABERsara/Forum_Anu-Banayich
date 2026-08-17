from typing import cast

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def decode_access_token(token: str) -> str:
    """
    Decode a JWT and return its subject (user id).

    Raises JWTError if the token is malformed/expired, has no subject,
    or is not an access token.
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != "access":
        raise JWTError("not an access token")
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise JWTError("missing subject")
    return user_id


def verify_password(plain: str, hashed: str) -> bool:
    return cast(bool, pwd_context.verify(plain, hashed))


def get_password_hash(password: str) -> str:
    return cast(str, pwd_context.hash(password))
