"""
Authentication endpoints.

POST /auth/register      – submit registration request
POST /auth/verify-otp    – verify OTP (email/phone)
POST /auth/login         – login, returns JWT
POST /auth/refresh       – refresh access token
POST /auth/resend-otp    – resend OTP
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.schemas.auth import (
    LoginRequest,
    OtpVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserProfile
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """
    Submit a new registration request.

    After this endpoint, the user is in PENDING_OTP status.
    An OTP is sent to their email.
    """
    return auth_service.register(db, data)


@router.post("/verify-otp", response_model=UserProfile)
def verify_otp(data: OtpVerifyRequest, db: Session = Depends(get_db)):
    """
    Verify the OTP received by email.

    After this, user moves to PENDING_APPROVAL status.
    """
    return auth_service.verify_otp(db, data.email, data.otp_code)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """
    Login with email + password.

    Returns JWT access_token (15 min) + refresh_token (7 days).
    """
    # TODO: call auth_service.login(db, data) and return the result
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    """Issue a new access token using a valid refresh token."""
    # TODO: call auth_service.refresh_token(db, data.refresh_token)
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/resend-otp", status_code=status.HTTP_200_OK)
def resend_otp(email: str, db: Session = Depends(get_db)):
    """Resend OTP to the given email."""
    auth_service.resend_otp(db, email)
    return {"detail": "קוד אימות נשלח מחדש"}
