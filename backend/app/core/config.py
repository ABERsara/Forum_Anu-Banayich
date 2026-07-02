"""
Application settings – loaded from .env file.

Copy .env.example to .env and fill in real values before running.
Never commit .env to git!
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------
    PROJECT_NAME: str = 'מערכת "אנו בניך"'
    API_V1_STR: str = "/api/v1"

    # ------------------------------------------------------------------
    # Security
    # Run: openssl rand -hex 32
    # ------------------------------------------------------------------
    SECRET_KEY: str = "dev-secret-change-in-production"

    # JWT access token: 15 minutes (spec section 9.2)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # JWT refresh token: 7 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OTP validity: 10 minutes
    OTP_EXPIRE_MINUTES: int = 10

    # ------------------------------------------------------------------
    # Database
    # SQLite for development, PostgreSQL for production
    # ------------------------------------------------------------------
    DATABASE_URL: str = "sqlite:///./dev.db"

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:4200",
        "http://localhost:3000",
    ]

    # ------------------------------------------------------------------
    # Email (SMTP)
    # Leave blank in development – emails are logged to console instead
    # ------------------------------------------------------------------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = 'noreply@anu-banayich.org.il'
    EMAIL_FROM_NAME: str = 'עמותת "אנו בניך"'

    # ------------------------------------------------------------------
    # File storage (S3 / Azure Blob)
    # Leave blank in development – files will be saved locally
    # ------------------------------------------------------------------
    STORAGE_BUCKET: str = ""
    STORAGE_REGION: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    # Presigned URL validity: 15 minutes (spec section 9.1)
    PRESIGNED_URL_EXPIRE_SECONDS: int = 900

    # ------------------------------------------------------------------
    # Moderation thresholds (can be tuned without code changes)
    # ------------------------------------------------------------------
    AUTO_HIDE_REPORT_COUNT: int = 2        # Reports before auto-hide
    AUTO_SUSPEND_VALID_REPORTS: int = 3    # Valid reports in 7 days → suspend
    AUTO_SUSPEND_DAYS_WINDOW: int = 7
    AUTO_SUSPEND_HOURS: int = 48
    FALSE_REPORT_LIMIT: int = 5            # False reports in 30 days → restrict
    FALSE_REPORT_DAYS_WINDOW: int = 30
    DM_BLOCK_AFTER_REPORTS: int = 3        # DM reports before auto-block


settings = Settings()
