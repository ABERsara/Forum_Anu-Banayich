"""
Unit tests for email_service.send_otp_email.

Covers three paths: dev fallback (SMTP_HOST empty), real SMTP send,
and SMTP failure (must never raise — registration depends on that).
"""

import logging

import pytest

from app.core.config import settings
from app.services import email_service


class _FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.calls = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append(("send_message", msg))


class _RaisingSMTP(_FakeSMTP):
    def login(self, user, password):
        raise ConnectionRefusedError("mock SMTP connection failure")


@pytest.fixture(autouse=True)
def _reset_smtp_settings(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    _FakeSMTP.instances.clear()
    yield


class TestBuildOtpMessage:
    def test_message_structure(self):
        msg = email_service._build_otp_message("test@example.com", "654321")

        assert msg["To"] == "test@example.com"
        assert msg["Subject"] == 'קוד אימות – עמותת "אנו בניך"'
        html = msg.get_payload(decode=True).decode("utf-8")
        assert "654321" in html
        assert 'dir="rtl"' in html


class TestSendOtpEmailDevFallback:
    def test_logs_otp_code(self, caplog):
        with caplog.at_level(logging.INFO):
            email_service.send_otp_email("test@example.com", "123456")
        assert "[DEV EMAIL] OTP 123456 -> test@example.com" in caplog.text

    def test_does_not_touch_smtp(self, monkeypatch):
        def _fail(*args, **kwargs):
            raise AssertionError("SMTP should not be used when SMTP_HOST is empty")

        monkeypatch.setattr(email_service.smtplib, "SMTP", _fail)
        email_service.send_otp_email("test@example.com", "123456")


class TestSendOtpEmailViaSmtp:
    def test_sends_via_smtp_with_starttls(self, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(settings, "SMTP_USER", "mailtrap-user")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "mailtrap-pass")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)

        email_service.send_otp_email("test@example.com", "654321")

        assert len(_FakeSMTP.instances) == 1
        smtp = _FakeSMTP.instances[0]
        assert smtp.host == "smtp.mailtrap.io"
        assert smtp.port == 587
        assert "ehlo" in smtp.calls
        assert "starttls" in smtp.calls
        assert ("login", "mailtrap-user", "mailtrap-pass") in smtp.calls

    def test_message_contains_otp_and_hebrew_rtl(self, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)

        email_service.send_otp_email("test@example.com", "654321")

        smtp = _FakeSMTP.instances[0]
        send_call = next(c for c in smtp.calls if isinstance(c, tuple) and c[0] == "send_message")
        msg = send_call[1]
        html = msg.get_payload(decode=True).decode("utf-8")
        assert "654321" in html
        assert 'dir="rtl"' in html
        assert msg["To"] == "test@example.com"

    def test_logs_success_after_send(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)

        with caplog.at_level(logging.INFO):
            email_service.send_otp_email("test@example.com", "654321")

        assert "[EMAIL] OTP sent → test@example.com" in caplog.text


class TestSendOtpEmailSmtpFailure:
    def test_does_not_raise_on_smtp_failure(self, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _RaisingSMTP)

        email_service.send_otp_email("test@example.com", "111111")  # must not raise

    def test_logs_error_on_smtp_failure(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _RaisingSMTP)

        with caplog.at_level(logging.ERROR):
            email_service.send_otp_email("test@example.com", "111111")

        assert "Failed to send OTP email" in caplog.text
