"""
Authentication endpoints.

POST /auth/register      – submit registration request
POST /auth/verify-otp    – verify OTP (email/phone)
POST /auth/login         – login, returns JWT
POST /auth/refresh       – refresh access token
POST /auth/resend-otp    – resend OTP
POST /auth/google        – login with a verified Firebase/Google ID token
POST /auth/google/link   – link a Google account to the current session
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.auth import (
    GoogleAuthRequest,
    LoginRequest,
    OtpVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    ResendOtpRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    """
    Submit a new registration request.

    After this endpoint, the user is in PENDING_OTP status.
    An OTP is sent to their email.
    """
    user = auth_service.register(db, data)
    return {"message": "נרשמת בהצלחה. בדוק את המייל לקוד OTP.", "user_id": user.id}


@router.post("/verify-otp")
def verify_otp(data: OtpVerifyRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    """
    Verify the OTP received by email.

    After this, user moves to PENDING_APPROVAL status.
    """
    auth_service.verify_otp(db, data.email, data.otp_code)
    return {"message": "אימות הצליח. הבקשה שלך ממתינה לאישור מנהלים."}


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """
    Login with email + password.

    Returns JWT access_token (15 min) + refresh_token (7 days).
    """
    return auth_service.login(db, data)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Issue a new access token using a valid refresh token."""
    return auth_service.refresh_token(db, data.refresh_token)


@router.post("/resend-otp", status_code=status.HTTP_200_OK)
def resend_otp(data: ResendOtpRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    """Resend OTP to the given email."""
    auth_service.resend_otp(db, data.email)
    # PROD: deviates from spec — spec defines "קוד OTP חדש נשלח.", message changed for consistency with other project messages. Reconsider before PROD.
    return {"message": "קוד אימות נשלח מחדש"}


@router.post("/google", response_model=TokenResponse)
def google_login(
    data: GoogleAuthRequest, db: Session = Depends(get_db)
) -> TokenResponse:
    """
    Login with a verified Firebase/Google ID token.

    Matches an existing ACTIVE account by google_uid, or by verified email on
    first use (auto-linking it). Returns the same JWT pair shape as /login.
    """
    return auth_service.google_login(db, data)


@router.post("/google/link")
def google_link(
    data: GoogleAuthRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, str]:
    """Link a verified Google account to the currently logged-in session."""
    auth_service.google_link(db, current_user, data)
    return {"message": "חשבון Google קושר בהצלחה."}
