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
    # Google Calendar / Meet (ABF-156)
    #
    # A different grant from FIREBASE_PROJECT_ID above. That one verifies an
    # ID token — it proves who the caller is and carries no authority to do
    # anything in the user's Google account. Creating a Meet means creating a
    # Calendar event on the professional's behalf, which is an OAuth
    # authorisation-code flow with its own consent screen, its own client
    # secret, and a refresh token stored per professional.
    #
    # Defaulted to empty rather than guarded like SECRET_KEY: an unconfigured
    # deployment must still start and serve everything else. The failure is
    # raised where the meeting is scheduled (google_meet_service), so it names
    # the missing setting instead of arriving as a 401 from Google.
    # ------------------------------------------------------------------
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # calendar.events, not the full calendar scope: this integration creates
    # events and never reads the professional's existing calendar. Asking for
    # less is also what the consent screen shows her.
    GOOGLE_CALENDAR_SCOPE: str = "https://www.googleapis.com/auth/calendar.events"

    # Where Google sends the browser back after consent: a page in the Angular
    # app, not an API route. The page posts the code and state to
    # POST /meetings/calendar/connect with the logged-in user's token, and the
    # API refuses a state issued to anyone else — a plain navigation to the API
    # carries no Authorization header to compare it with. The client secret
    # still never leaves the API: the code is useless without it.
    # Must match a redirect URI registered in the Google Cloud console exactly.
    GOOGLE_REDIRECT_URI_MEET: str = "http://localhost:4200/meetings/calendar/callback"

    # Google Calendar needs an end time; the form asks only for a start
    # (ABF-156 leaves choosing a duration to a later ticket). Each meeting
    # stores the value it was created with — see Meeting.duration_minutes.
    MEETING_DEFAULT_DURATION_MINUTES: int = 60

    # The token and event calls sit inside a request the professional is
    # waiting on, so they fail fast rather than holding the worker open —
    # same reasoning as GEMINI_TIMEOUT_SECONDS below.
    GOOGLE_CALENDAR_TIMEOUT_SECONDS: int = 10

    # ------------------------------------------------------------------
    # Gemini embeddings (agent knowledge base retrieval)
    # ------------------------------------------------------------------
    # Deliberately defaulted to empty rather than guarded like SECRET_KEY
    # above: an absent key must not stop the API from starting, because every
    # part of the system other than knowledge-base indexing works without it.
    # rag_service validates it at the point of the call instead, so the failure
    # names the missing key rather than surfacing as a 401 from Google.
    GEMINI_API_KEY: str = ""

    # Bound to the vector(768) column the migration creates. This model's own
    # default is 3072, so rag_service asks for 768 explicitly on every request;
    # a model that cannot produce 768 at all needs a migration and a re-index of
    # every existing entry, not just a new value here.
    #
    # A model name belongs in config precisely because these are retired on a
    # schedule: embedding-001 went on 2025-10-30 and text-embedding-004 on
    # 2026-01-14. This one has no announced shutdown date yet, which is not the
    # same as never. See https://ai.google.dev/gemini-api/docs/deprecations
    # before changing it.
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"

    # One embedding call sits inside a request the professional is waiting on,
    # so it fails fast rather than holding the worker open.
    GEMINI_TIMEOUT_SECONDS: int = 10

    # ------------------------------------------------------------------
    # AI agent – answer generation (ABF-122)
    # ------------------------------------------------------------------
    # Which llm_service provider generates the agent's answers. Swapping this
    # to another registered name (see llm_service.register_provider) is the
    # whole change needed to move off Gemini — no caller names a provider
    # class, so nothing else has to be edited or redeployed.
    LLM_PROVIDER: str = "gemini"

    # The Gemini model that writes the answer, as distinct from
    # GEMINI_EMBED_MODEL above, which only turns text into vectors. Two
    # settings because they are two model families on two deprecation
    # schedules: retrieval keeps working when the chat model is retired, and
    # the reverse.
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Hard ceiling on one generation call. A chat request holds a worker for
    # its whole duration, so this is what stops a slow provider from taking
    # the API down with it. Longer than GEMINI_TIMEOUT_SECONDS because
    # generating paragraphs is genuinely slower than embedding a sentence.
    LLM_TIMEOUT_SECONDS: float = 20.0

    # ------------------------------------------------------------------
    # AI agent – conversation limits (can be tuned without code changes)
    # ------------------------------------------------------------------
    # Messages one user may send to the agents in a rolling 24 hours, counted
    # across every domain rather than per agent: the cost being capped is the
    # provider bill, and that is one bill.
    AGENT_RATE_LIMIT_PER_DAY: int = 30

    # Longest question accepted, in characters. Enforced by the Pydantic
    # schema (422), not by the provider's token limit.
    AGENT_MAX_MESSAGE_LENGTH: int = 1000

    # How close a passage has to be to the question before it is allowed to
    # ground an answer. rag_service.retrieve() ranks and returns the k nearest
    # chunks whatever the question was — it has no notion of "near enough" —
    # so without a floor here, "מה תחזית מזג האוויר מחר?" comes back with the
    # five least-unrelated paragraphs in a housing-rights knowledge base and
    # the agent's refusal to answer off-topic questions rests entirely on the
    # model obeying rule 2 of its prompt. With a floor it is a property of the
    # code: nothing clears it, the provider is never called, and the reader is
    # sent to human advice (agent_service._retrieve_for).
    #
    # The scale is RetrievedChunk.score — 1 - cosine distance, so 1.0 is
    # identical, 0.0 unrelated, negative actively contrary.
    #
    # A setting rather than a constant because the right number is a property
    # of the deployment's own content and of GEMINI_EMBED_MODEL, not of this
    # code: it has to be calibrated once the knowledge base is real, and
    # re-calibrated if the embedding model changes. Both failure directions
    # are visible, which is what makes tuning it safe — too high and the agent
    # refers questions it could have answered, too low and it quotes
    # paragraphs about something else. 0.35 is deliberately a low floor: it
    # rejects the plainly unrelated and leaves the marginal calls to the
    # prompt, because the expensive mistake at this stage is refusing a widow
    # an answer the association wrote for her.
    AGENT_MIN_RELEVANCE_SCORE: float = 0.35

    # How many of the conversation's most recent *turns* – a question and the
    # answer it got – are replayed into the prompt, so "ומה לגבי הילדים שלי"
    # resolves against what came before it. 3 turns is at most 6 messages.
    # Costs tokens on every request, which is why the ticket asks for an
    # environment variable rather than a constant: raise it if follow-ups lose
    # the thread, lower it if the bill grows faster than usage — no deploy.
    AGENT_HISTORY_TURNS: int = 3

    # ------------------------------------------------------------------
    # Moderation thresholds (can be tuned without code changes)
    # ------------------------------------------------------------------
    AUTO_HIDE_REPORT_COUNT: int = 2  # Reports before auto-hide
    #: §7.2's third row ("אירוע חוזר משמעותי") reads 2+ upheld incidents in 7
    #: days; this default holds the 3 it was written with, and ABF-154 — the
    #: ticket that enforces it, through report_service._check_auto_suspension()
    #: — settles the two numbers on 3 rather than re-pointing this one at 2.
    #:
    #: Because the measure is the heaviest of the three. DM_BLOCK_AFTER_REPORTS
    #: withdraws one action for 48 hours and FALSE_REPORT_LIMIT withdraws
    #: another; this one takes the account away, and it should not be the rule
    #: with the lowest bar. Read through `settings` at the moment the threshold
    #: is evaluated, never inlined at the call site (FINDINGS M-01), so a first
    #: real run can move it in either direction without a deploy.
    AUTO_SUSPEND_VALID_REPORTS: int = 3
    AUTO_SUSPEND_DAYS_WINDOW: int = 7
    AUTO_SUSPEND_HOURS: int = 48

    # ------------------------------------------------------------------
    # Automatic restrictions (spec §5.3 מה"ק, §7.2) — ABF-116
    #
    # Every number below is read through `settings` at the moment a
    # threshold is evaluated, never inlined at the call site, because the
    # ticket's own note is that these have to be re-calibrated after the
    # first real run. Inlining is the mistake FINDINGS M-01 records for
    # AUTO_HIDE_REPORT_COUNT: a setting nothing reads looks tunable and is
    # not.
    #
    # Direction A — the repeatedly-reported sender. Upheld (VALID) reports
    # only: a report that a moderator dismissed is not evidence of anything,
    # and CLOSED_ACCOUNT_DELETED is the system closing a report, not a
    # finding against anyone.
    # ------------------------------------------------------------------
    DM_BLOCK_AFTER_REPORTS: int = 3  # Upheld reports in the window → restrict
    DM_BLOCK_DAYS_WINDOW: int = 30
    #: How long the sending restriction lasts. 48 hours to match
    #: AUTO_SUSPEND_HOURS above — the platform's one stated duration for a
    #: temporary automatic measure, and §5.3 gives none of its own.
    DM_BLOCK_HOURS: int = 48

    # ------------------------------------------------------------------
    # Direction B — the member whose reports keep being dismissed. Not a
    # ban on reporting: §7.2 asks for a daily allowance, so she can still
    # report the thing that happens to her today.
    # ------------------------------------------------------------------
    FALSE_REPORT_LIMIT: int = 5  # False reports in 30 days → restrict
    FALSE_REPORT_DAYS_WINDOW: int = 30
    #: Reports still allowed per day while the restriction is in force.
    RESTRICTED_REPORTS_PER_DAY: int = 3
    #: How long the reporting allowance lasts, in days.
    FALSE_REPORT_RESTRICTION_DAYS: int = 30

    # ------------------------------------------------------------------
    # Private messaging storage cap (spec section 5.3)
    # ------------------------------------------------------------------
    # "up to 1,000 messages per conversation". Enforced on every send by
    # forum_service._enforce_conversation_limit(): oldest-first (FIFO), and
    # never a message that still carries an open report. Read through
    # `settings` rather than inlined at the call site, so tuning it here
    # actually changes behaviour (the mistake FINDINGS M-01 records for
    # AUTO_HIDE_REPORT_COUNT).
    MAX_MESSAGES_PER_CONVERSATION: int = 1000

    # How long a private message is kept before the scheduled retention job
    # deletes it (spec §5.3/§9.4: "ניקוי אוטומטי לשיחה אחר 3 שנים"). See
    # retention_service.purge_expired_direct_messages() (ABF-117).
    DIRECT_MESSAGE_RETENTION_DAYS: int = 1095  # 3 years

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
