"""
Authentication service.

Handles registration, OTP, login, JWT issuance.

TODO list for junior developer:
  [ ] implement register() – create user, hash password, send OTP
  [ ] implement verify_otp() – compare code, mark pending_approval
  [x] implement login() – verify password, issue JWT pair
  [x] implement refresh_token() – validate refresh JWT, issue new access token
"""

import random
import string
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AccountStatus, UserRole
from app.core.security import ALGORITHM, get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.email_service import send_otp_email


def _generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def _create_token(subject: str, expires_delta: timedelta, token_type: str = "access") -> str:
    expire = datetime.now(UTC) + expires_delta
    payload = {"sub": subject, "exp": expire, "type": token_type}
    return str(jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM))


def register(db: Session, data: RegisterRequest) -> User:
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        # PROD: deviates from spec — spec defines 400, changed to 409 Conflict for semantic correctness (valid request conflicting with existing resource). Reconsider before PROD.
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
        # PROD: intentionally 400 instead of 404 — prevents User Enumeration Attack.
        raise HTTPException(status_code=400, detail="הפרטים שהוזנו שגויים")
    expires_at = user.otp_expires_at
    if expires_at is None or expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        # PROD: deviates from spec — spec defines a generic message for all OTP errors. Distinguishing "expired" from "wrong code" slightly weakens User Enumeration protection. Reconsider before PROD.
        raise HTTPException(status_code=400, detail="קוד האימות פג תוקף")
    if user.otp_code != otp_code:
        raise HTTPException(status_code=400, detail="הפרטים שהוזנו שגויים")
    user.account_status = AccountStatus.PENDING_APPROVAL
    user.otp_code = None
    user.otp_expires_at = None
    db.commit()
    db.refresh(user)
    return user


def login(db: Session, data: LoginRequest) -> TokenResponse:
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="אימות נכשל. בדוק/י מייל וסיסמה.")
    if user.account_status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="החשבון אינו פעיל. פנה/י למנהל.")
    access = _create_token(user.id, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access")
    refresh = _create_token(user.id, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), "refresh")
    return TokenResponse(access_token=access, refresh_token=refresh, token_type="bearer")


def refresh_token(db: Session, refresh_tok: str) -> TokenResponse:
    try:
        payload = jwt.decode(refresh_tok, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="טוקן רענון לא תקין.") from None
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="טוקן רענון לא תקין.")
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="טוקן רענון לא תקין.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.account_status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=401, detail="טוקן רענון לא תקין.")
    access = _create_token(user.id, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access")
    return TokenResponse(access_token=access, refresh_token=refresh_tok, token_type="bearer")


def resend_otp(db: Session, email: str) -> None:
    user = db.query(User).filter(User.email == email).first()
    if not user or user.account_status != AccountStatus.PENDING_OTP:
        # PROD: intentionally 400 instead of 404 — prevents User Enumeration Attack.
        raise HTTPException(status_code=400, detail="לא ניתן לשלוח קוד אימות")
    otp = _generate_otp()
    user.otp_code = otp
    user.otp_expires_at = datetime.now(UTC) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    db.commit()
    send_otp_email(user.email, otp)
