"""
Application settings – loaded from .env file.

Copy .env.example to .env and fill in real values before running.
Never commit .env to git!
"""

import sys
from typing import Self

from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ----------------------------------------------------------------------
# SECRET_KEY guard rails (ABF-96)
#
# SECRET_KEY signs and verifies every JWT the API issues. A key that is
# public knowledge means anyone can forge an admin token, so outside
# development the application refuses to start rather than boot insecure.
# ----------------------------------------------------------------------

# The convenience default assigned to Settings.SECRET_KEY below.
DEFAULT_SECRET_KEY = "dev-secret-change-in-production"

# The placeholder shipped in backend/.env.example — copying that file to
# .env and deploying it is the likeliest way to reach production with a
# key that is readable in this repository.
ENV_EXAMPLE_SECRET_KEY = "change-me-in-production-use-openssl-rand-hex-32"

# Every key value that is public because it lives in this repository.
KNOWN_INSECURE_SECRET_KEYS = frozenset({DEFAULT_SECRET_KEY, ENV_EXAMPLE_SECRET_KEY})

# 32 characters is the shortest key still worth signing HS256 tokens with.
MIN_SECRET_KEY_LENGTH = 32

# ----------------------------------------------------------------------
# MESSAGE_ENCRYPTION_KEY guard rails (ABF-118, same template as ABF-96)
#
# MESSAGE_ENCRYPTION_KEY encrypts every private message at rest. A key that
# is public knowledge means anyone with DB access can read private messages,
# so outside development the application refuses to start rather than boot
# insecure — identical reasoning to SECRET_KEY above.
# ----------------------------------------------------------------------

# The convenience default assigned to Settings.MESSAGE_ENCRYPTION_KEY below.
DEFAULT_MESSAGE_ENCRYPTION_KEY = "dev-message-key-change-in-production-0000"

# The placeholder shipped in backend/.env.example.
ENV_EXAMPLE_MESSAGE_ENCRYPTION_KEY = "change-me-in-production-use-openssl-rand-hex-32"

# Every key value that is public because it lives in this repository.
KNOWN_INSECURE_MESSAGE_ENCRYPTION_KEYS = frozenset(
    {DEFAULT_MESSAGE_ENCRYPTION_KEY, ENV_EXAMPLE_MESSAGE_ENCRYPTION_KEY}
)

# Same threshold as SECRET_KEY: 32 characters is the shortest secret still
# worth deriving an AES-256 key from. app/core/encryption.py hashes this
# string (SHA-256) to get the actual 32 raw key bytes, so this does not need
# to be hex — "openssl rand -hex 32" is just a convenient way to generate a
# long random string, same as the SECRET_KEY guidance above.
MIN_MESSAGE_ENCRYPTION_KEY_LENGTH = 32

# Environments allowed to keep the default key. Everything else is treated
# as production — deployments must set ENVIRONMENT explicitly.
DEVELOPMENT_ENVIRONMENTS = frozenset({"development", "dev", "local", "test"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------
    PROJECT_NAME: str = 'מערכת "אנו בניך"'
    API_V1_STR: str = "/api/v1"

    # Deployment environment. Any value outside DEVELOPMENT_ENVIRONMENTS
    # enforces the SECRET_KEY rules below, so hosted deployments must set
    # ENVIRONMENT=production.
    ENVIRONMENT: str = "development"

    # ------------------------------------------------------------------
    # Security
    # Run: openssl rand -hex 32
    # ------------------------------------------------------------------
    SECRET_KEY: str = "dev-secret-change-in-production"

    # Private-message encryption (AES-256-GCM) — SHA-256-hashed into the
    # actual 32-byte key by app/core/encryption.py. Run: openssl rand -hex 32
    MESSAGE_ENCRYPTION_KEY: str = "dev-message-key-change-in-production-0000"

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
    EMAIL_FROM: str = "noreply@anu-banayich.org.il"
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
    # Google / Firebase OAuth
    # Required for POST /auth/google – find this in Firebase Console → Project settings
    # ------------------------------------------------------------------
    FIREBASE_PROJECT_ID: str = ""

    # ------------------------------------------------------------------
    # AI agent – LLM provider (ABF-121 embeddings, ABF-122 generation)
    #
    # GEMINI_API_KEY is required for POST /agents/{domain_id}/chat to answer a
    # question its knowledge base covers: without it that request is a 503,
    # deliberately, rather than a quiet fallback to "I have no information" —
    # a missing key must look like a fault, not like an answer. A question the
    # knowledge base does *not* cover still works with no key at all, because
    # no provider is called for it.
    # ------------------------------------------------------------------
    GEMINI_API_KEY: str = ""

    # Which llm_service provider serves generation. Swapping this to another
    # registered name (see llm_service.register_provider) is the whole change
    # needed to move off Gemini – no caller touches a provider class.
    LLM_PROVIDER: str = "gemini"

    # Gemini model used for generation. Configurable so a model deprecation
    # is an environment change, not a deploy.
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Hard ceiling on one generation call. A chat request holds a worker for
    # its whole duration, so this is what stops a slow provider from taking
    # the API down with it.
    LLM_TIMEOUT_SECONDS: float = 20.0

    # ------------------------------------------------------------------
    # AI agent – conversation limits (can be tuned without code changes)
    # ------------------------------------------------------------------
    # Messages one user may send to the agents in a rolling 24 hours,
    # counted across every domain rather than per agent: the cost being
    # capped is the provider bill, and that is one bill.
    AGENT_RATE_LIMIT_PER_DAY: int = 30

    # Longest question accepted, in characters. Enforced by the Pydantic
    # schema (422), not by the provider's token limit.
    AGENT_MAX_MESSAGE_LENGTH: int = 1000

    # How many of the conversation's most recent *turns* – a question and the
    # answer it got – are replayed into the prompt, so "ומה לגבי הילדים שלי"
    # resolves against what came before it. 3 turns is at most 6 messages.
    # Costs tokens on every request, which is why it is tunable without a
    # deploy: raise it if follow-ups lose the thread, lower it if the bill
    # grows faster than usage.
    AGENT_HISTORY_TURNS: int = 3

    # ------------------------------------------------------------------
    # Moderation thresholds (can be tuned without code changes)
    # ------------------------------------------------------------------
    AUTO_HIDE_REPORT_COUNT: int = 2  # Reports before auto-hide
    AUTO_SUSPEND_VALID_REPORTS: int = 3  # Valid reports in 7 days → suspend
    AUTO_SUSPEND_DAYS_WINDOW: int = 7
    AUTO_SUSPEND_HOURS: int = 48
    FALSE_REPORT_LIMIT: int = 5  # False reports in 30 days → restrict
    FALSE_REPORT_DAYS_WINDOW: int = 30
    DM_BLOCK_AFTER_REPORTS: int = 3  # DM reports before auto-block

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @model_validator(mode="after")
    def _validate_secret_key(self) -> Self:
        """Reject a forgeable JWT signing key outside development.

        Never include the key itself in an error message — these messages
        land in deployment logs. Report its length instead.
        """
        if self.ENVIRONMENT.strip().lower() in DEVELOPMENT_ENVIRONMENTS:
            return self

        env = self.ENVIRONMENT
        key = self.SECRET_KEY.strip()

        if not key:
            raise ValueError(
                f"SECRET_KEY is missing or empty while ENVIRONMENT={env!r}. "
                "The API cannot sign JWTs without it."
            )

        if key in KNOWN_INSECURE_SECRET_KEYS:
            raise ValueError(
                f"SECRET_KEY is still a placeholder committed to this repository, "
                f"while ENVIRONMENT={env!r}. Its value is public, so anyone could "
                "forge an admin token."
            )

        if len(key) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY is too short: {len(key)} characters, but at least "
                f"{MIN_SECRET_KEY_LENGTH} are required while ENVIRONMENT={env!r}."
            )

        return self

    @model_validator(mode="after")
    def _validate_message_encryption_key(self) -> Self:
        """Reject a forgeable private-message encryption key outside development.

        Never include the key itself in an error message — these messages
        land in deployment logs. Report its length instead.
        """
        if self.ENVIRONMENT.strip().lower() in DEVELOPMENT_ENVIRONMENTS:
            return self

        env = self.ENVIRONMENT
        key = self.MESSAGE_ENCRYPTION_KEY.strip()

        if not key:
            raise ValueError(
                f"MESSAGE_ENCRYPTION_KEY is missing or empty while "
                f"ENVIRONMENT={env!r}. The API cannot encrypt private messages "
                "without it."
            )

        if key in KNOWN_INSECURE_MESSAGE_ENCRYPTION_KEYS:
            raise ValueError(
                f"MESSAGE_ENCRYPTION_KEY is still a placeholder committed to "
                f"this repository, while ENVIRONMENT={env!r}. Its value is "
                "public, so anyone with DB access could read private messages."
            )

        if len(key) < MIN_MESSAGE_ENCRYPTION_KEY_LENGTH:
            raise ValueError(
                f"MESSAGE_ENCRYPTION_KEY is too short: {len(key)} characters, "
                f"but at least {MIN_MESSAGE_ENCRYPTION_KEY_LENGTH} are required "
                f"while ENVIRONMENT={env!r}."
            )

        return self


def _format_startup_error(exc: ValidationError) -> str:
    """Render a ValidationError as an actionable message, not a traceback."""
    problems = "\n".join(
        f"  - {error['msg'].removeprefix('Value error, ')}" for error in exc.errors()
    )
    return (
        "\n"
        "============================================================\n"
        "  CONFIGURATION ERROR - the application cannot start\n"
        "============================================================\n"
        f"{problems}\n"
        "\n"
        "  How to fix:\n"
        "    1. Generate a strong key:  openssl rand -hex 32\n"
        "    2. Set it as the SECRET_KEY environment variable on the host\n"
        "       (Render: Dashboard > Service > Environment > Add).\n"
        "    3. Redeploy. Previously issued JWTs stop validating, so users\n"
        "       will have to log in again.\n"
        "\n"
        "  Local development is unaffected: ENVIRONMENT defaults to\n"
        "  'development', where this check is skipped.\n"
        "============================================================\n"
    )


try:
    settings = Settings()
except ValidationError as exc:
    print(_format_startup_error(exc), file=sys.stderr)
    sys.exit(1)
