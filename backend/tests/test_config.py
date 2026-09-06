"""Tests for the SECRET_KEY startup validator (ABF-96).

Settings is instantiated once at import time in app.core.config, so these
tests build fresh Settings objects instead of re-importing the module.
Every instance is built with _env_file=None: without it a developer's local
.env would leak into the assertions and the suite would pass or fail
depending on whose machine it runs on.
"""

import pytest
from pydantic import ValidationError

from app.core.config import (
    DEFAULT_MESSAGE_ENCRYPTION_KEY,
    DEFAULT_SECRET_KEY,
    ENV_EXAMPLE_MESSAGE_ENCRYPTION_KEY,
    ENV_EXAMPLE_SECRET_KEY,
    MIN_MESSAGE_ENCRYPTION_KEY_LENGTH,
    MIN_SECRET_KEY_LENGTH,
    Settings,
    _format_startup_error,
)

# Stands in for the output of `openssl rand -hex 32`.
VALID_SECRET_KEY = "9f2c" * 16
VALID_MESSAGE_ENCRYPTION_KEY = "a1b2" * 16


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Drop inherited values so each test states its own configuration."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("MESSAGE_ENCRYPTION_KEY", raising=False)


def build_settings(
    monkeypatch,
    environment=None,
    secret_key=None,
    message_encryption_key=None,
) -> Settings:
    """Build Settings from the given env vars, ignoring any local .env file.

    Tests that only care about SECRET_KEY and build a fully-successful
    Settings (no pytest.raises) in production must also supply a valid
    message_encryption_key, or ABF-118's validator rejects the otherwise-good
    SECRET_KEY-only config too — same as production requires a real
    SECRET_KEY regardless of which test is focused on.
    """
    if environment is not None:
        monkeypatch.setenv("ENVIRONMENT", environment)
    if secret_key is not None:
        monkeypatch.setenv("SECRET_KEY", secret_key)
    if message_encryption_key is not None:
        monkeypatch.setenv("MESSAGE_ENCRYPTION_KEY", message_encryption_key)
    return Settings(_env_file=None)


# ----------------------------------------------------------------------
# Production rejects insecure keys
# ----------------------------------------------------------------------


def test_production_rejects_unset_secret_key(monkeypatch):
    """No SECRET_KEY on the host falls back to the committed default."""
    with pytest.raises(ValidationError) as exc_info:
        build_settings(monkeypatch, environment="production")

    assert "SECRET_KEY" in str(exc_info.value)


def test_production_rejects_empty_secret_key(monkeypatch):
    with pytest.raises(ValidationError) as exc_info:
        build_settings(monkeypatch, environment="production", secret_key="")

    assert "missing or empty" in str(exc_info.value)


def test_production_rejects_whitespace_only_secret_key(monkeypatch):
    with pytest.raises(ValidationError) as exc_info:
        build_settings(monkeypatch, environment="production", secret_key="   ")

    assert "missing or empty" in str(exc_info.value)


def test_production_rejects_config_default_secret_key(monkeypatch):
    with pytest.raises(ValidationError) as exc_info:
        build_settings(
            monkeypatch, environment="production", secret_key=DEFAULT_SECRET_KEY
        )

    assert "placeholder" in str(exc_info.value)


def test_production_rejects_env_example_secret_key(monkeypatch):
    """The value in backend/.env.example is public too, so it must be blocked."""
    with pytest.raises(ValidationError) as exc_info:
        build_settings(
            monkeypatch, environment="production", secret_key=ENV_EXAMPLE_SECRET_KEY
        )

    assert "placeholder" in str(exc_info.value)


def test_production_rejects_short_secret_key(monkeypatch):
    short_key = "a" * (MIN_SECRET_KEY_LENGTH - 1)

    with pytest.raises(ValidationError) as exc_info:
        build_settings(monkeypatch, environment="production", secret_key=short_key)

    message = str(exc_info.value)
    assert "too short" in message
    assert str(MIN_SECRET_KEY_LENGTH - 1) in message


@pytest.mark.parametrize("environment", ["PRODUCTION", "Production", " production "])
def test_environment_match_is_case_and_whitespace_insensitive(monkeypatch, environment):
    """A capitalised ENVIRONMENT must not silently bypass the check."""
    with pytest.raises(ValidationError):
        build_settings(
            monkeypatch, environment=environment, secret_key=DEFAULT_SECRET_KEY
        )


@pytest.mark.parametrize("environment", ["staging", "prod", "render"])
def test_unknown_environments_are_treated_as_production(monkeypatch, environment):
    with pytest.raises(ValidationError):
        build_settings(
            monkeypatch, environment=environment, secret_key=DEFAULT_SECRET_KEY
        )


# ----------------------------------------------------------------------
# Production accepts a real key
# ----------------------------------------------------------------------


def test_production_accepts_valid_secret_key(monkeypatch):
    settings = build_settings(
        monkeypatch,
        environment="production",
        secret_key=VALID_SECRET_KEY,
        message_encryption_key=VALID_MESSAGE_ENCRYPTION_KEY,
    )

    assert settings.SECRET_KEY == VALID_SECRET_KEY
    assert settings.ENVIRONMENT == "production"


def test_production_accepts_key_at_exactly_minimum_length(monkeypatch):
    settings = build_settings(
        monkeypatch,
        environment="production",
        secret_key="b" * MIN_SECRET_KEY_LENGTH,
        message_encryption_key=VALID_MESSAGE_ENCRYPTION_KEY,
    )

    assert len(settings.SECRET_KEY) == MIN_SECRET_KEY_LENGTH


# ----------------------------------------------------------------------
# Development must keep working untouched
# ----------------------------------------------------------------------


def test_development_without_secret_key_starts_with_the_default(monkeypatch):
    """The critical case: local development must not break."""
    settings = build_settings(monkeypatch)

    assert settings.ENVIRONMENT == "development"
    assert settings.SECRET_KEY == DEFAULT_SECRET_KEY


@pytest.mark.parametrize(
    "environment", ["development", "dev", "local", "test", "DEV", "Local"]
)
def test_development_environments_skip_validation(monkeypatch, environment):
    settings = build_settings(monkeypatch, environment=environment, secret_key="short")

    assert settings.SECRET_KEY == "short"


# ----------------------------------------------------------------------
# The key value never reaches the logs
# ----------------------------------------------------------------------


def test_error_message_never_leaks_the_secret_key(monkeypatch):
    leaky_key = "hunter2-too-short-to-pass"

    with pytest.raises(ValidationError) as exc_info:
        build_settings(monkeypatch, environment="production", secret_key=leaky_key)

    message = str(exc_info.value)
    assert leaky_key not in message
    assert str(len(leaky_key)) in message


def test_startup_error_is_actionable_and_not_a_traceback(monkeypatch):
    leaky_key = "hunter2-too-short-to-pass"

    with pytest.raises(ValidationError) as exc_info:
        build_settings(monkeypatch, environment="production", secret_key=leaky_key)

    output = _format_startup_error(exc_info.value)

    assert "openssl rand -hex 32" in output
    assert "SECRET_KEY" in output
    assert "too short" in output
    assert leaky_key not in output
    assert "Traceback" not in output
    assert "Value error," not in output  # Pydantic's prefix is stripped


def test_startup_error_is_ascii_only(monkeypatch):
    """The banner is written to stderr, which is not always UTF-8."""
    with pytest.raises(ValidationError) as exc_info:
        build_settings(monkeypatch, environment="production", secret_key="")

    _format_startup_error(exc_info.value).encode("ascii")


# ----------------------------------------------------------------------
# MESSAGE_ENCRYPTION_KEY startup validator (ABF-118) — same rules as
# SECRET_KEY above, since it's the identical guard-rail template.
# ----------------------------------------------------------------------


def _build_with_valid_secret_key(monkeypatch, **kwargs) -> Settings:
    """A valid SECRET_KEY, so only MESSAGE_ENCRYPTION_KEY is under test."""
    return build_settings(monkeypatch, secret_key=VALID_SECRET_KEY, **kwargs)


def test_production_rejects_unset_message_encryption_key(monkeypatch):
    with pytest.raises(ValidationError) as exc_info:
        _build_with_valid_secret_key(monkeypatch, environment="production")

    assert "MESSAGE_ENCRYPTION_KEY" in str(exc_info.value)


def test_production_rejects_empty_message_encryption_key(monkeypatch):
    with pytest.raises(ValidationError) as exc_info:
        _build_with_valid_secret_key(
            monkeypatch, environment="production", message_encryption_key=""
        )

    assert "missing or empty" in str(exc_info.value)


def test_production_rejects_config_default_message_encryption_key(monkeypatch):
    with pytest.raises(ValidationError) as exc_info:
        _build_with_valid_secret_key(
            monkeypatch,
            environment="production",
            message_encryption_key=DEFAULT_MESSAGE_ENCRYPTION_KEY,
        )

    assert "placeholder" in str(exc_info.value)


def test_production_rejects_env_example_message_encryption_key(monkeypatch):
    """The value in backend/.env.example is public too, so it must be blocked."""
    with pytest.raises(ValidationError) as exc_info:
        _build_with_valid_secret_key(
            monkeypatch,
            environment="production",
            message_encryption_key=ENV_EXAMPLE_MESSAGE_ENCRYPTION_KEY,
        )

    assert "placeholder" in str(exc_info.value)


def test_production_rejects_short_message_encryption_key(monkeypatch):
    short_key = "a" * (MIN_MESSAGE_ENCRYPTION_KEY_LENGTH - 1)

    with pytest.raises(ValidationError) as exc_info:
        _build_with_valid_secret_key(
            monkeypatch,
            environment="production",
            message_encryption_key=short_key,
        )

    message = str(exc_info.value)
    assert "too short" in message
    assert str(MIN_MESSAGE_ENCRYPTION_KEY_LENGTH - 1) in message


def test_production_accepts_valid_message_encryption_key(monkeypatch):
    settings = _build_with_valid_secret_key(
        monkeypatch,
        environment="production",
        message_encryption_key=VALID_MESSAGE_ENCRYPTION_KEY,
    )

    assert settings.MESSAGE_ENCRYPTION_KEY == VALID_MESSAGE_ENCRYPTION_KEY


def test_development_without_message_encryption_key_starts_with_the_default(
    monkeypatch,
):
    """The critical case: local development must not break."""
    settings = build_settings(monkeypatch)

    assert settings.MESSAGE_ENCRYPTION_KEY == DEFAULT_MESSAGE_ENCRYPTION_KEY


def test_error_message_never_leaks_the_message_encryption_key(monkeypatch):
    leaky_key = "hunter2-too-short-to-pass"

    with pytest.raises(ValidationError) as exc_info:
        _build_with_valid_secret_key(
            monkeypatch, environment="production", message_encryption_key=leaky_key
        )

    message = str(exc_info.value)
    assert leaky_key not in message
    assert str(len(leaky_key)) in message
