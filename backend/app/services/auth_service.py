"""
Authentication service.

Handles registration, OTP, login, JWT issuance.

TODO list for junior developer:
  [ ] implement register() – create user, hash password, send OTP
  [ ] implement verify_otp() – compare code, mark pending_approval
  [ ] implement login() – verify password, issue JWT pair
  [ ] implement refresh_token() – validate refresh JWT, issue new access token
"""

import random
import string
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from jose import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AccountStatus, UserRole
from app.core.security import ALGORITHM, get_password_hash
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.email_service import send_otp_email


def _generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def _create_token(subject: str, expires_delta: timedelta, token_type: str = "access") -> str:
    expire = datetime.now(UTC) + expires_delta
    payload = {"sub": subject, "exp": expire, "type": token_type}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def register(db: Session, data: RegisterRequest) -> User:
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="כתובת המייל כבר רשומה במערכת")
    hashed = get_password_hash(data.password)
    user = User(
        email=data.email,
        password_hash=hashed,
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        birth_date=data.birth_date,
        user_type=data.user_type,
        sector=data.sector,
        id_number=data.id_number,
        role=UserRole.USER,
        account_status=AccountStatus.PENDING_OTP,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    otp = _generate_otp()
    user.otp_code = otp
    user.otp_expires_at = datetime.now(UTC) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    db.commit()
    send_otp_email(user.email, otp)
    return user


def verify_otp(db: Session, email: str, otp_code: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="משתמש לא נמצא")
    if user.otp_code != otp_code:
        raise HTTPException(status_code=400, detail="קוד האימות שגוי")
    expires_at = user.otp_expires_at
    if expires_at is None or expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="קוד האימות פג תוקף")
    user.account_status = AccountStatus.PENDING_APPROVAL
    user.otp_code = None
    user.otp_expires_at = None
    db.commit()
    db.refresh(user)
    return user


def login(db: Session, data: LoginRequest) -> TokenResponse:
    """
    Authenticate user and return JWT tokens.

    TODO:
      1. Find user by email
      2. Verify password with verify_password()
      3. Check account_status == ACTIVE (raise 403 otherwise)
      4. Create access token (15 min) and refresh token (7 days)
      5. Return TokenResponse
    """
    # TODO: implement this function
    raise NotImplementedError("login() is not yet implemented")


def refresh_token(db: Session, refresh_tok: str) -> TokenResponse:
    """
    Issue new access token using a valid refresh token.

    TODO:
      1. Decode the refresh JWT
      2. Verify it has type="refresh"
      3. Load user from DB, verify still ACTIVE
      4. Issue new access token
      5. Return TokenResponse (can reuse same refresh token)
    """
    # TODO: implement this function
    raise NotImplementedError("refresh_token() is not yet implemented")


def resend_otp(db: Session, email: str) -> None:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="משתמש לא נמצא")
    if user.account_status != AccountStatus.PENDING_OTP:
        raise HTTPException(status_code=400, detail="לא ניתן לשלוח קוד אימות במצב זה")
    otp = _generate_otp()
    user.otp_code = otp
    user.otp_expires_at = datetime.now(UTC) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    db.commit()
    send_otp_email(user.email, otp)
