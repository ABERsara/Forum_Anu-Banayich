"""
Pydantic schemas for authentication endpoints.

RegisterRequest  → POST /auth/register
LoginRequest     → POST /auth/login
TokenResponse    → response from login / refresh
OtpVerifyRequest → POST /auth/verify-otp
"""

from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.constants import Sector, UserType


class RegisterRequest(BaseModel):
    """Step 1+2 of registration: personal details + contact."""

    first_name: str = Field(..., min_length=2, max_length=100, examples=["שרה"])
    last_name: str = Field(..., min_length=2, max_length=100, examples=["לוי"])
    email: EmailStr = Field(..., examples=["sarah@example.com"])
    phone: str = Field(..., min_length=9, max_length=15, examples=["0501234567"])
    birth_date: date = Field(..., examples=["1985-03-15"])
    user_type: UserType = Field(..., examples=[UserType.WIDOW])
    sector: Sector = Field(..., examples=[Sector.SEPHARDIC])
    id_number: str = Field(..., min_length=7, max_length=20, examples=["123456789"])
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("phone")
    @classmethod
    def phone_digits_only(cls, v: str) -> str:
        digits = v.replace("-", "").replace(" ", "")
        if not digits.isdigit():
            raise ValueError("מספר הטלפון חייב להכיל ספרות בלבד")
        return digits


class OtpVerifyRequest(BaseModel):
    """Step 2: OTP verification (email or phone)."""

    email: EmailStr
    otp_code: str = Field(..., min_length=4, max_length=10)


class ResendOtpRequest(BaseModel):
    """POST /auth/resend-otp body."""

    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Returned on successful login or token refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)
