"""
Unit tests for the email_service senders that really talk to SMTP: the OTP,
the registration verdicts, the two new-question alerts and the answer alert.

Each covers three paths: dev fallback (SMTP_HOST empty), real SMTP send,
and SMTP failure (must never raise — registration and answering depend on that).
"""

import email as email_lib
import logging
from collections import namedtuple
from email.header import decode_header, make_header
from email.utils import parseaddr

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
        send_call = next(
            c for c in smtp.calls if isinstance(c, tuple) and c[0] == "send_message"
        )
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


class TestBuildAnswerMessage:
    def test_message_structure(self):
        msg = email_service._build_answer_message("asker@example.com")

        assert msg["To"] == "asker@example.com"
        assert msg["Subject"] == 'התקבלה תשובה לשאלתך – עמותת "אנו בניך"'
        html = msg.get_payload(decode=True).decode("utf-8")
        assert 'dir="rtl"' in html

    def test_does_not_quote_the_consultation(self):
        """SPEC §6.4 — a private consultation must not leave the platform."""
        msg = email_service._build_answer_message("asker@example.com")

        html = msg.get_payload(decode=True).decode("utf-8")
        assert "השאלות שלי" in html  # points the asker back to the site instead


class TestSendAnswerNotificationDevFallback:
    def test_logs_the_query_id(self, caplog):
        with caplog.at_level(logging.INFO):
            email_service.send_answer_notification("asker@example.com", "query-42")
        assert "[DEV EMAIL] Answer received for query query-42" in caplog.text

    def test_does_not_touch_smtp(self, monkeypatch):
        def _fail(*args, **kwargs):
            raise AssertionError("SMTP should not be used when SMTP_HOST is empty")

        monkeypatch.setattr(email_service.smtplib, "SMTP", _fail)
        email_service.send_answer_notification("asker@example.com", "query-42")


class TestSendAnswerNotificationViaSmtp:
    def test_sends_via_smtp_with_starttls(self, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(settings, "SMTP_USER", "mailtrap-user")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "mailtrap-pass")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)

        email_service.send_answer_notification("asker@example.com", "query-42")

        assert len(_FakeSMTP.instances) == 1
        smtp = _FakeSMTP.instances[0]
        assert smtp.host == "smtp.mailtrap.io"
        assert "starttls" in smtp.calls
        assert ("login", "mailtrap-user", "mailtrap-pass") in smtp.calls
        send_call = next(
            c for c in smtp.calls if isinstance(c, tuple) and c[0] == "send_message"
        )
        assert send_call[1]["To"] == "asker@example.com"

    def test_logs_success_after_send(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)

        with caplog.at_level(logging.INFO):
            email_service.send_answer_notification("asker@example.com", "query-42")

        assert "[EMAIL] Answer notification sent for query query-42" in caplog.text


class TestSendAnswerNotificationSmtpFailure:
    def test_does_not_raise_on_smtp_failure(self, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _RaisingSMTP)

        # Must not raise: the answer is already committed by the time we get here.
        email_service.send_answer_notification("asker@example.com", "query-42")

    def test_logs_error_on_smtp_failure(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _RaisingSMTP)

        with caplog.at_level(logging.ERROR):
            email_service.send_answer_notification("asker@example.com", "query-42")

        assert "Failed to send answer notification email" in caplog.text


# ---------------------------------------------------------------------------
# ABF-107 — the four senders this ticket switched from log-only to real mail.
#
# They share one shape, so they share one table: what to call, what the dev
# fallback logged before this ticket (which must not change), what a real send
# logs, and what a failed send logs.
# ---------------------------------------------------------------------------

_Sender = namedtuple("_Sender", "send to dev_log sent_log error_log")

_REJECTION_REASON = "המסמכים שצורפו אינם קריאים"

ACTIVATED_SENDERS = [
    pytest.param(
        _Sender(
            send=lambda: email_service.send_approval_email("dana@example.com", "דנה"),
            to="dana@example.com",
            dev_log="[EMAIL] Registration approved → dana@example.com",
            sent_log="[EMAIL] Approval email sent → dana@example.com",
            error_log="Failed to send approval email",
        ),
        id="approval",
    ),
    pytest.param(
        _Sender(
            send=lambda: email_service.send_rejection_email(
                "dana@example.com", "דנה", _REJECTION_REASON
            ),
            to="dana@example.com",
            dev_log=(
                f"[EMAIL] Registration rejected → dana@example.com, "
                f"reason: {_REJECTION_REASON}"
            ),
            sent_log="[EMAIL] Rejection email sent → dana@example.com",
            error_log="Failed to send rejection email",
        ),
        id="rejection",
    ),
    pytest.param(
        _Sender(
            send=lambda: email_service.send_direct_question_notification(
                "pro@example.com", "query-7"
            ),
            to="pro@example.com",
            dev_log="[EMAIL] שאלה ישירה query-7 → pro@example.com",
            sent_log="[EMAIL] Direct question notification sent for query query-7",
            error_log="Failed to send direct question notification email",
        ),
        id="direct-question",
    ),
    pytest.param(
        _Sender(
            send=lambda: email_service.send_domain_question_notification(
                "pro@example.com", "query-7"
            ),
            to="pro@example.com",
            dev_log="[EMAIL] שאלה כללית query-7 → pro@example.com",
            sent_log="[EMAIL] Domain question notification sent for query query-7",
            error_log="Failed to send domain question notification email",
        ),
        id="domain-question",
    ),
]


def _sent_html(smtp):
    """The HTML body of the single message handed to a fake SMTP session."""
    send_call = next(
        c for c in smtp.calls if isinstance(c, tuple) and c[0] == "send_message"
    )
    return send_call[1], send_call[1].get_payload(decode=True).decode("utf-8")


def _from_on_the_wire(msg):
    """
    The (display name, address) a receiving MTA parses out of From.

    Serialising and re-parsing is the point: in memory From is whatever Python
    was handed, and only the bytes show whether the address survived the RFC
    2047 encoding of the Hebrew display name.
    """
    received = email_lib.message_from_bytes(msg.as_bytes())
    name, address = parseaddr(received["From"])
    return str(make_header(decode_header(name))), address


@pytest.mark.parametrize("sender", ACTIVATED_SENDERS)
class TestActivatedSendersDevFallback:
    def test_logs_the_same_line_as_before_the_ticket(self, sender, caplog):
        """SMTP_HOST empty in development → console log, unchanged wording."""
        with caplog.at_level(logging.INFO):
            sender.send()

        assert sender.dev_log in caplog.text

    def test_does_not_touch_smtp(self, sender, monkeypatch):
        def _fail(*args, **kwargs):
            raise AssertionError("SMTP should not be used when SMTP_HOST is empty")

        monkeypatch.setattr(email_service.smtplib, "SMTP", _fail)
        sender.send()


@pytest.mark.parametrize("sender", ACTIVATED_SENDERS)
class TestActivatedSendersViaSmtp:
    def test_sends_via_smtp_with_starttls(self, sender, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(settings, "SMTP_USER", "mailtrap-user")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "mailtrap-pass")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)

        sender.send()

        assert len(_FakeSMTP.instances) == 1
        smtp = _FakeSMTP.instances[0]
        assert smtp.host == "smtp.mailtrap.io"
        assert smtp.port == 587
        assert "starttls" in smtp.calls
        assert ("login", "mailtrap-user", "mailtrap-pass") in smtp.calls

    def test_message_is_hebrew_rtl_and_addressed_to_the_recipient(
        self, sender, monkeypatch
    ):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)

        sender.send()

        msg, html = _sent_html(_FakeSMTP.instances[0])
        assert msg["To"] == sender.to
        assert _from_on_the_wire(msg) == (
            'עמותת "אנו בניך"',
            "noreply@anu-banayich.org.il",
        )
        assert 'dir="rtl">' in html
        assert "שלום" in html

    def test_logs_success_after_send(self, sender, monkeypatch, caplog):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)

        with caplog.at_level(logging.INFO):
            sender.send()

        assert sender.sent_log in caplog.text


@pytest.mark.parametrize("sender", ACTIVATED_SENDERS)
class TestActivatedSendersSmtpFailure:
    def test_does_not_raise(self, sender, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _RaisingSMTP)

        # The approval/rejection/question is already committed by now — a mail
        # server that is down must not undo it.
        sender.send()

    def test_logs_the_failure(self, sender, monkeypatch, caplog):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _RaisingSMTP)

        with caplog.at_level(logging.ERROR):
            sender.send()

        assert sender.error_log in caplog.text
        assert sender.to in caplog.text


class TestBuildMessage:
    def test_wraps_every_body_in_one_rtl_div(self):
        msg = email_service._build_message("a@example.com", "נושא", "<p>גוף</p>")

        html = msg.get_payload(decode=True).decode("utf-8")
        assert html == '<div dir="rtl"><p>גוף</p></div>'
        assert msg["Subject"] == "נושא"
        assert msg["To"] == "a@example.com"

    def test_sender_address_survives_the_hebrew_display_name(self):
        """The name is RFC 2047-encoded; the address must stay in the clear, or
        what an MTA reads out of From is an encoded-word and not an address."""
        msg = email_service._build_message("a@example.com", "נושא", "<p>גוף</p>")

        name, address = _from_on_the_wire(msg)
        assert address == "noreply@anu-banayich.org.il"
        assert name == 'עמותת "אנו בניך"'

    def test_hebrew_subject_reaches_the_reader_decodable(self):
        msg = email_service._build_message("a@example.com", "נושא בעברית", "<p>גוף</p>")

        received = email_lib.message_from_bytes(msg.as_bytes())
        assert str(make_header(decode_header(received["Subject"]))) == "נושא בעברית"


class TestBuildApprovalMessage:
    def test_greets_the_user_by_name(self):
        msg = email_service._build_approval_message("dana@example.com", "דנה")

        html = msg.get_payload(decode=True).decode("utf-8")
        assert msg["Subject"] == 'ההרשמה שלך אושרה – עמותת "אנו בניך"'
        assert "שלום דנה," in html
        assert "אושרה" in html


class TestBuildRejectionMessage:
    def test_states_the_reason_the_admin_recorded(self):
        msg = email_service._build_rejection_message(
            "dana@example.com", "דנה", _REJECTION_REASON
        )

        html = msg.get_payload(decode=True).decode("utf-8")
        assert msg["Subject"] == 'עדכון בנוגע לבקשת ההרשמה שלך – עמותת "אנו בניך"'
        assert _REJECTION_REASON in html


class TestUserWrittenTextIsEscaped:
    """A name or a rejection reason is text, never markup: it arrives in a mail
    signed by the association, where a working link would be a phishing gift."""

    def test_name_is_escaped(self):
        msg = email_service._build_approval_message(
            "dana@example.com", '<a href="http://evil.example">דנה</a>'
        )

        html = msg.get_payload(decode=True).decode("utf-8")
        assert "<a href=" not in html
        assert "&lt;a href=" in html

    def test_reason_is_escaped(self):
        msg = email_service._build_rejection_message(
            "dana@example.com", "דנה", "<script>alert(1)</script> & עוד"
        )

        html = msg.get_payload(decode=True).decode("utf-8")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "&amp; עוד" in html


class TestBuildQuestionMessage:
    def test_direct_and_general_differ_by_subject(self):
        direct = email_service._build_question_message(
            "pro@example.com", is_general=False
        )
        general = email_service._build_question_message(
            "pro@example.com", is_general=True
        )

        assert direct["Subject"] == 'שאלה חדשה הופנתה אליך – עמותת "אנו בניך"'
        assert general["Subject"] == 'שאלה חדשה בתחום שלך – עמותת "אנו בניך"'

    def test_direct_says_the_question_was_addressed_to_this_professional(self):
        msg = email_service._build_question_message("pro@example.com", is_general=False)

        html = msg.get_payload(decode=True).decode("utf-8")
        assert "הופנתה אליך שאלה חדשה" in html

    def test_general_says_the_question_is_in_this_domain(self):
        msg = email_service._build_question_message("pro@example.com", is_general=True)

        html = msg.get_payload(decode=True).decode("utf-8")
        assert "בתחום המקצועי שלך" in html

    @pytest.mark.parametrize("is_general", [False, True])
    def test_points_to_the_site_without_quoting_the_question(self, is_general):
        """SPEC §6.4 — the asker decides on the site who sees their name; an
        email that carried the question would decide it for them."""
        msg = email_service._build_question_message(
            "pro@example.com", is_general=is_general
        )

        html = msg.get_payload(decode=True).decode("utf-8")
        assert "שאלות ממתינות לתשובה" in html  # the professional's own screen
        assert "פרטי השואל אינם נשלחים במייל" in html


class TestQuestionIdStaysOutOfTheMail:
    def test_query_id_is_logged_but_not_sent(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)

        with caplog.at_level(logging.INFO):
            email_service.send_direct_question_notification(
                "pro@example.com", "query-7"
            )

        _msg, html = _sent_html(_FakeSMTP.instances[0])
        assert "query-7" not in html
        assert "query-7" in caplog.text
