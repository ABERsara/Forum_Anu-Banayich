"""
Email service.

send_otp_email sends real mail via SMTP when SMTP_HOST is configured.
The other notifications below are still stubs.

TODO (when ready for production):
  [ ] Send real email for approval/rejection/moderator/suspension/question notifications
  [ ] Load templates from HTML files
  [ ] Add retry logic for failed sends
  [ ] Add unsubscribe links where required by law
"""

import logging
import smtplib
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_otp_email(email: str, otp_code: str) -> None:
    """Send OTP verification code to a new registrant."""
    if not settings.SMTP_HOST:
        logger.info(f"[DEV EMAIL] OTP {otp_code} -> {email}")
        return

    html = (
        f'<div dir="rtl">'
        f"<p>שלום,</p>"
        f"<p>ברוך הבא ל-{settings.PROJECT_NAME}. הנה קוד האימות שלך:</p>"
        f"<h1>{otp_code}</h1>"
        f"<p>הקוד תקף ל-{settings.OTP_EXPIRE_MINUTES} דקות.</p>"
        f"<p>לא נרשמת? פשוט התעלם מהמייל הזה.</p>"
        f"</div>"
    )
    # PROD: single MIMEText, no MIMEMultipart("alternative") — there's no plain-text
    # alternative to choose between yet. Add one back if a plain-text fallback is added.
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = 'קוד אימות – עמותת "אנו בניך"'
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
    msg["To"] = email

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
            s.ehlo()
            s.starttls()
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)
    except Exception as exc:
        logger.error(f"[EMAIL] Failed to send OTP email to {email}: {exc}")
        return

    logger.info(f"[EMAIL] OTP sent → {email}")


def send_approval_email(email: str, first_name: str) -> None:
    """Notify a user that their registration was approved."""
    logger.info(f"[EMAIL] Registration approved → {email}")
    # TODO: send real email


def send_rejection_email(email: str, first_name: str, reason: str) -> None:
    """Notify a user that their registration was rejected."""
    logger.info(f"[EMAIL] Registration rejected → {email}, reason: {reason}")
    # TODO: send real email


def send_moderator_alert(moderator_email: str, report_id: str, content_preview: str) -> None:
    """Notify a moderator of a new report (1st report on content)."""
    logger.info(f"[EMAIL] Moderator alert for report {report_id} → {moderator_email}")
    # TODO: send real email


def send_urgent_moderator_alert(moderator_email: str, report_id: str) -> None:
    """Urgent notification – content auto-hidden after 2nd report."""
    logger.info(f"[EMAIL] URGENT moderator alert for report {report_id} → {moderator_email}")
    # TODO: send real email


def send_suspension_notification(email: str, hours: int, reason: str) -> None:
    """Notify a user that their account was suspended."""
    logger.info(f"[EMAIL] Suspension notification → {email}, {hours}h, reason: {reason}")
    # TODO: send real email


def send_question_notification(professional_email: str, query_id: str, is_general: bool) -> None:
    """Notify a professional of a new question."""
    label = "שאלה כללית" if is_general else "שאלה ישירה"
    logger.info(f"[EMAIL] {label} {query_id} → {professional_email}")
    # TODO: send real email


def send_answer_notification(asker_email: str, query_id: str) -> None:
    """Notify the asker that their question was answered."""
    logger.info(f"[EMAIL] Answer received for query {query_id} → {asker_email}")
    # TODO: send real email
