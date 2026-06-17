"""
Email service – stub.

In production this would use SMTP or a service like SendGrid / AWS SES.
For now, all functions just print to the console so development can proceed
without setting up a real mail server.

TODO (when ready for production):
  [ ] Replace print() calls with actual SMTP sending
  [ ] Load templates from HTML files
  [ ] Add retry logic for failed sends
  [ ] Add unsubscribe links where required by law
"""

import logging

logger = logging.getLogger(__name__)


def send_otp_email(email: str, otp_code: str) -> None:
    """Send OTP verification code to a new registrant."""
    logger.info(f"[EMAIL] OTP {otp_code} → {email}")
    # TODO: send real email


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
