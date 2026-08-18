"""
Email service.

Every sender has the same three steps: fall back to a console log when
SMTP_HOST is empty, build a MIMEText message, hand it to _send_via_smtp.
The OTP, registration and consultation notifications all send real mail;
the moderation ones below are still stubs.

TODO (when ready for production):
  [ ] Send real email for moderator/suspension/SLA notifications
  [ ] Load templates from HTML files
  [ ] Add retry logic for failed sends
  [ ] Add unsubscribe links where required by law
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from html import escape

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_message(email: str, subject: str, body: str) -> MIMEText:
    """
    Wrap one email body in the envelope every notification shares.

    The RTL wrapper lives here rather than in each body, so no sender can ship
    Hebrew that renders left-to-right. `body` is HTML that is already escaped.
    """
    # single MIMEText, no MIMEMultipart("alternative") — there's no plain-text
    # alternative to choose between yet. Add one back if a plain-text fallback is added.
    msg = MIMEText(f'<div dir="rtl">{body}</div>', "html", "utf-8")
    msg["Subject"] = subject
    # formataddr, not an f-string: it RFC 2047-encodes the Hebrew display name
    # on its own and leaves the address in the clear. Encoding the two together
    # hides the address inside an encoded-word, and what a receiving MTA then
    # parses out of From is "=?utf-8?b?...?=" rather than an address.
    msg["From"] = formataddr((settings.EMAIL_FROM_NAME, settings.EMAIL_FROM))
    msg["To"] = email
    return msg


def _build_otp_message(email: str, otp_code: str) -> MIMEText:
    body = (
        f"<p>שלום,</p>"
        f"<p>ברוך הבא ל-{settings.PROJECT_NAME}. הנה קוד האימות שלך:</p>"
        f"<h1>{otp_code}</h1>"
        f"<p>הקוד תקף ל-{settings.OTP_EXPIRE_MINUTES} דקות.</p>"
        f"<p>לא נרשמת? פשוט התעלם מהמייל הזה.</p>"
    )
    return _build_message(email, 'קוד אימות – עמותת "אנו בניך"', body)


def _send_via_smtp(msg: MIMEText, purpose: str) -> bool:
    """
    Deliver an already-built message over SMTP.

    Returns True on success, False if the send failed – a failed notification
    is logged and swallowed, never raised, because no caller may be rolled back
    by a mail server being down (delivery alerting is tracked in finding I-04).
    """
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
            s.ehlo()
            s.starttls()
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)
    except Exception as exc:
        logger.error(f"[EMAIL] Failed to send {purpose} email to {msg['To']}: {exc}")
        return False

    return True


def send_otp_email(email: str, otp_code: str) -> None:
    """Send OTP verification code to a new registrant."""
    if not settings.SMTP_HOST:
        logger.info(f"[DEV EMAIL] OTP {otp_code} -> {email}")
        return

    if _send_via_smtp(_build_otp_message(email, otp_code), "OTP"):
        logger.info(f"[EMAIL] OTP sent → {email}")


def _build_approval_message(email: str, first_name: str) -> MIMEText:
    body = (
        f"<p>שלום {escape(first_name)},</p>"
        f"<p>בקשת ההרשמה שלך ל{settings.PROJECT_NAME} אושרה.</p>"
        f"<p>מעכשיו אפשר להתחבר לאתר עם כתובת המייל הזו, לקרוא ולכתוב בפורום "
        f"ולפנות לאנשי המקצוע של העמותה.</p>"
        f"<p>שמחים שהצטרפת.</p>"
    )
    return _build_message(email, 'ההרשמה שלך אושרה – עמותת "אנו בניך"', body)


def send_approval_email(email: str, first_name: str) -> None:
    """Notify a user that their registration was approved."""
    if not settings.SMTP_HOST:
        logger.info(f"[EMAIL] Registration approved → {email}")
        return

    if _send_via_smtp(_build_approval_message(email, first_name), "approval"):
        logger.info(f"[EMAIL] Approval email sent → {email}")


def _build_rejection_message(email: str, first_name: str, reason: str) -> MIMEText:
    body = (
        f"<p>שלום {escape(first_name)},</p>"
        f"<p>בקשת ההרשמה שלך ל{settings.PROJECT_NAME} נבדקה ולא אושרה.</p>"
        f"<p>הסיבה שנרשמה: {escape(reason)}</p>"
        f"<p>לבירור נוסף אפשר לפנות לעמותה.</p>"
    )
    return _build_message(
        email, 'עדכון בנוגע לבקשת ההרשמה שלך – עמותת "אנו בניך"', body
    )


def send_rejection_email(email: str, first_name: str, reason: str) -> None:
    """
    Notify a user that their registration was rejected, with the reason.

    The name and the reason are the only user-written text this module puts in
    a message: escape() is what keeps either of them from becoming markup in a
    mail signed by the association.
    """
    if not settings.SMTP_HOST:
        logger.info(f"[EMAIL] Registration rejected → {email}, reason: {reason}")
        return

    msg = _build_rejection_message(email, first_name, reason)
    if _send_via_smtp(msg, "rejection"):
        logger.info(f"[EMAIL] Rejection email sent → {email}")


def send_moderator_alert(
    moderator_email: str, report_id: str, content_preview: str
) -> None:
    """Notify a moderator of a new report (1st report on content)."""
    logger.info(f"[EMAIL] Moderator alert for report {report_id} → {moderator_email}")
    # TODO: send real email


def send_urgent_moderator_alert(moderator_email: str, report_id: str) -> None:
    """Urgent notification – content auto-hidden after 2nd report."""
    logger.info(
        f"[EMAIL] URGENT moderator alert for report {report_id} → {moderator_email}"
    )
    # TODO: send real email


def send_suspension_notification(email: str, hours: int, reason: str) -> None:
    """Notify a user that their account was suspended."""
    logger.info(
        f"[EMAIL] Suspension notification → {email}, {hours}h, reason: {reason}"
    )
    # TODO: send real email


def _build_question_message(email: str, *, is_general: bool) -> MIMEText:
    """
    Build the new-question notification for a professional.

    A direct question and a domain question differ by one sentence, so they
    share a body — but they keep separate subjects, because a professional who
    receives both has only the subject line to tell them apart by.

    Neither the question nor the asker is named. The asker chooses per question
    whether their real name is shown (`show_real_name`), and that choice is
    honoured on the site, where an email cannot leak past it (SPEC §6.4).
    """
    subject, opening = (
        (
            'שאלה חדשה בתחום שלך – עמותת "אנו בניך"',
            "נשאלה שאלה חדשה בתחום המקצועי שלך",
        )
        if is_general
        else (
            'שאלה חדשה הופנתה אליך – עמותת "אנו בניך"',
            "הופנתה אליך שאלה חדשה",
        )
    )
    body = (
        f"<p>שלום,</p>"
        f"<p>{opening} ב{settings.PROJECT_NAME}.</p>"
        f'<p>השאלה ממתינה לך במסך "שאלות ממתינות לתשובה" באתר.</p>'
        f"<p>מטעמי פרטיות תוכן השאלה ופרטי השואל אינם נשלחים במייל.</p>"
    )
    return _build_message(email, subject, body)


def send_direct_question_notification(professional_email: str, query_id: str) -> None:
    """Notify a professional of a new question addressed to them directly."""
    if not settings.SMTP_HOST:
        logger.info(f"[EMAIL] שאלה ישירה {query_id} → {professional_email}")
        return

    # query_id names the send in the log; it is deliberately not in the mail.
    msg = _build_question_message(professional_email, is_general=False)
    if _send_via_smtp(msg, "direct question notification"):
        logger.info(f"[EMAIL] Direct question notification sent for query {query_id}")


def send_domain_question_notification(professional_email: str, query_id: str) -> None:
    """Notify a professional of a new general question in their domain."""
    if not settings.SMTP_HOST:
        logger.info(f"[EMAIL] שאלה כללית {query_id} → {professional_email}")
        return

    msg = _build_question_message(professional_email, is_general=True)
    if _send_via_smtp(msg, "domain question notification"):
        logger.info(f"[EMAIL] Domain question notification sent for query {query_id}")


def _build_answer_message(email: str) -> MIMEText:
    body = (
        f"<p>שלום,</p>"
        f"<p>איש המקצוע השיב לשאלה ששאלת ב{settings.PROJECT_NAME}.</p>"
        f'<p>התשובה ממתינה לך באזור "השאלות שלי" באתר.</p>'
        f"<p>מטעמי פרטיות התשובה עצמה אינה נשלחת במייל.</p>"
    )
    return _build_message(email, 'התקבלה תשובה לשאלתך – עמותת "אנו בניך"', body)


def send_answer_notification(asker_email: str, query_id: str) -> None:
    """
    Notify the asker that their question was answered.

    The mail says only that an answer is waiting – neither the question nor the
    answer is quoted, so a private consultation never leaves the platform in an
    unencrypted inbox (SPEC §6.4).
    """
    if not settings.SMTP_HOST:
        logger.info(f"[DEV EMAIL] Answer received for query {query_id} → {asker_email}")
        return

    if _send_via_smtp(_build_answer_message(asker_email), "answer notification"):
        logger.info(f"[EMAIL] Answer notification sent for query {query_id}")


def send_sla_escalation_alert(
    admin_email: str, user_id: str, pending_email: str
) -> None:
    """Notify a senior admin that a registration has been pending 7+ days."""
    logger.info(
        f"[EMAIL] SLA escalation for registration {user_id} ({pending_email}) → {admin_email}"
    )
    # TODO: send real email
