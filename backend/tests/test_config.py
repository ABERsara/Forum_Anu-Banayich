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
    DEFAULT_SECRET_KEY,
    ENV_EXAMPLE_SECRET_KEY,
    MIN_SECRET_KEY_LENGTH,
    Settings,
    _format_startup_error,
)

# Stands in for the output of `openssl rand -hex 32`.
VALID_SECRET_KEY = "9f2c" * 16


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Drop inherited values so each test states its own configuration."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)


def build_settings(monkeypatch, environment=None, secret_key=None) -> Settings:
    """Build Settings from the given env vars, ignoring any local .env file."""
    if environment is not None:
        monkeypatch.setenv("ENVIRONMENT", environment)
    if secret_key is not None:
        monkeypatch.setenv("SECRET_KEY", secret_key)
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
        monkeypatch, environment="production", secret_key=VALID_SECRET_KEY
    )

    assert settings.SECRET_KEY == VALID_SECRET_KEY
    assert settings.ENVIRONMENT == "production"


def test_production_accepts_key_at_exactly_minimum_length(monkeypatch):
    settings = build_settings(
        monkeypatch,
        environment="production",
        secret_key="b" * MIN_SECRET_KEY_LENGTH,
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
