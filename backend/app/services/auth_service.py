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
from typing import Any

from fastapi import HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AccountStatus, UserRole
from app.core.security import ALGORITHM, get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import (
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.email_service import send_otp_email

# Reused across requests: caches Google's public signing certs internally.
_google_auth_request = google_requests.Request()


def _generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def _create_token(
    subject: str, expires_delta: timedelta, token_type: str = "access"
) -> str:
    expire = datetime.now(UTC) + expires_delta
    payload = {"sub": subject, "exp": expire, "type": token_type}
    return str(jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM))


def _generate_and_assign_otp(user: User) -> str:
    # send_otp_email is intentionally not folded in here — register() and
    # resend_otp() commit at different points (register only after db.add;
    # resend_otp immediately), so each caller sends the email itself once
    # its own commit has succeeded.
    otp = _generate_otp()
    user.otp_code = otp
    user.otp_expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.OTP_EXPIRE_MINUTES
    )
    return otp


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
    otp = _generate_and_assign_otp(user)
    db.add(user)
    db.commit()
    db.refresh(user)
    # PROD: sent after commit by design — the OTP is already persisted at this point,
    # so a failed send is recoverable via resend_otp() rather than leaving orphaned state.
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


def _check_active_or_reactivate(db: Session, user: User) -> None:
    """
    Business rule shared by every login path (password or Google): a
    temporary suspension that has expired auto-reactivates the account;
    otherwise only ACTIVE accounts may proceed. Raises 403 otherwise.
    """
    if user.is_suspended:
        still_suspended = (
            user.suspended_until is not None
            and user.suspended_until.replace(tzinfo=UTC) > datetime.now(UTC)
        )
        if still_suspended:
            raise HTTPException(
                status_code=403, detail="החשבון מושעה זמנית. נסה שוב מאוחר יותר."
            )
        user.account_status = AccountStatus.ACTIVE
        user.is_suspended = False
        user.suspended_until = None
        db.commit()

    if user.account_status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="החשבון אינו פעיל. פנה/י למנהל.")


def login(db: Session, data: LoginRequest) -> TokenResponse:
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="אימות נכשל. בדוק/י מייל וסיסמה.")

    _check_active_or_reactivate(db, user)

    access = _create_token(
        user.id, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access"
    )
    refresh = _create_token(
        user.id, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), "refresh"
    )
    return TokenResponse(
        access_token=access, refresh_token=refresh, token_type="bearer"
    )


def _verify_firebase_token(id_token: str) -> dict[str, Any]:
    """
    Verify a Firebase ID token's signature against Google's public certs and
    confirm it was issued for our Firebase project. Raises 401 on any
    failure (bad signature, wrong/expired project, malformed token).
    """
    try:
        # google-auth ships no type stubs, so this call is untyped from mypy's view.
        claims: dict[str, Any] | None = google_id_token.verify_firebase_token(  # type: ignore[no-untyped-call]
            id_token, _google_auth_request, audience=settings.FIREBASE_PROJECT_ID
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=401, detail="אימות Google נכשל. נסה/י שוב."
        ) from exc
    if claims is None or not claims.get("email") or not claims.get("email_verified"):
        raise HTTPException(status_code=401, detail="אימות Google נכשל. נסה/י שוב.")
    return claims


def google_login(db: Session, data: GoogleAuthRequest) -> TokenResponse:
    """
    Log in with a verified Firebase/Google ID token.

    Looks up the user by google_uid first; if this is their first Google
    sign-in, falls back to matching by verified email and auto-links
    google_uid to that account (no separate "link" step required). Does not
    create new accounts — Google login is a shortcut for already-registered,
    ACTIVE accounts only.
    """
    claims = _verify_firebase_token(data.id_token)
    google_uid: str = claims["sub"]
    email: str = claims["email"]

    user = db.query(User).filter(User.google_uid == google_uid).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            # Unlike password login/OTP, this doesn't need user-enumeration
            # protection: reaching this branch already requires controlling
            # a real Google account for this exact email (Google signs the
            # claim), which is a much stronger bar than guessing an email.
            raise HTTPException(
                status_code=403, detail="אין חשבון מקושר למייל זה. יש להירשם תחילה."
            )
        if user.google_uid is not None and user.google_uid != google_uid:
            raise HTTPException(
                status_code=409, detail="כתובת המייל מקושרת לחשבון Google אחר."
            )

    _check_active_or_reactivate(db, user)

    if user.google_uid is None:
        user.google_uid = google_uid
        db.commit()

    access = _create_token(
        user.id, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access"
    )
    refresh = _create_token(
        user.id, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), "refresh"
    )
    return TokenResponse(
        access_token=access, refresh_token=refresh, token_type="bearer"
    )


def google_link(db: Session, current_user: User, data: GoogleAuthRequest) -> None:
    """
    Explicitly link a verified Google account to the current (logged-in)
    session. Rejects if that Google account is already linked elsewhere.
    """
    claims = _verify_firebase_token(data.id_token)
    google_uid: str = claims["sub"]

    conflict = (
        db.query(User)
        .filter(User.google_uid == google_uid, User.id != current_user.id)
        .first()
    )
    if conflict is not None:
        raise HTTPException(
            status_code=409, detail="חשבון Google זה כבר מקושר למשתמש אחר."
        )

    current_user.google_uid = google_uid
    db.commit()


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
    access = _create_token(
        user.id, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access"
    )
    return TokenResponse(
        access_token=access, refresh_token=refresh_tok, token_type="bearer"
    )


def resend_otp(db: Session, email: str) -> None:
    user = db.query(User).filter(User.email == email).first()
    if not user or user.account_status != AccountStatus.PENDING_OTP:
        # PROD: intentionally 400 instead of 404 — prevents User Enumeration Attack.
        raise HTTPException(status_code=400, detail="לא ניתן לשלוח קוד אימות")
    otp = _generate_and_assign_otp(user)
    db.commit()
    send_otp_email(user.email, otp)
