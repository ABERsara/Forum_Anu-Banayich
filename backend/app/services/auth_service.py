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

from jose import jwt
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
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def register(db: Session, data: RegisterRequest) -> User:
    """
    Step 1: Create a new user account and send OTP.

    TODO:
      1. Check if email already exists → raise 400
      2. Hash the password with get_password_hash()
      3. Create the User object and save to DB
      4. Generate OTP, save it + expiry on the user, send email
      5. Return the created user
    """
    # TODO: implement this function
    raise NotImplementedError("register() is not yet implemented")


def verify_otp(db: Session, email: str, otp_code: str) -> User:
    """
    Step 2: Verify OTP and move user to pending_approval status.

    TODO:
      1. Find user by email
      2. Check OTP code matches and hasn't expired
      3. Update status to PENDING_APPROVAL
      4. Clear the OTP from the DB
      5. Return the user
    """
    # TODO: implement this function
    raise NotImplementedError("verify_otp() is not yet implemented")


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
    """
    Resend OTP to a user still in PENDING_OTP status.

    TODO:
      1. Find user by email
      2. Verify status is PENDING_OTP
      3. Generate new OTP, update expiry
      4. Send email
    """
    # TODO: implement this function
    raise NotImplementedError("resend_otp() is not yet implemented")
