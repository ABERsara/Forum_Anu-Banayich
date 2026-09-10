"""
The catalogue of every user-facing message the API returns.

One entry per message, one translation per supported language. Nothing here
imports from the rest of the app on purpose: `app.core.i18n` imports this
module, so keeping it pure data is what stops the two from forming a cycle.

Why a catalogue at all
----------------------
Before ABF-137 the Hebrew text was written at the point it was raised, which
made the language of a response a property of *where the code ran* rather than
of *who asked*. A member reading the site in English still got Hebrew back from
every 4xx. Routing every message through a key lets `i18n.translate()` pick the
language from the request's Accept-Language header at the moment it is raised.

Keys are `<domain>.<message>`, matching the frontend's Transloco convention
(`profile.title`, `admin.dashboard.*`). They are the same keys in both
languages, and `tests/test_i18n_catalogue.py` fails if the two sides ever drift
apart, if a key is unused, or if a key is used without being defined here.

Reuse across domains is deliberate
----------------------------------
A few keys are raised from more than one module — `auth.email_taken` from both
auth_service and user_service, `forum.post_not_found` from report_service,
`professionals.query_not_found` from like_service. These are the *same* message
to the reader, and they render identically today; giving each caller its own key
would let one copy drift and leave the platform saying two different things
about one situation.

Not in here, on purpose
-----------------------
- `forum_service._DM_FORBIDDEN_MESSAGE` / `_INVALID_CURSOR_MESSAGE` already
  travel to the client *as* translation keys, which the Angular client resolves
  itself (`core/utils/error-key.util.ts`). Translating them here would replace a
  key the client recognises with prose it does not, and the chat screen would
  quietly drop from a specific message to its generic fallback. They stay as
  they are; unifying the two mechanisms needs a frontend change and is a ticket
  of its own.
- Email templates (`email_service`), which the ticket defers whole.
- `core/constants.py`. Its enum *values* are English slugs, which the client
  renders through its own label maps (ABF-127) — nothing there reaches a member
  through this API. The Hebrew in the file is real string data, not comments:
  `USER_TYPE_LABELS` and `SECTOR_LABELS`. Their one reader is
  `professional_service._build_alias()`, which ABF-137 defers — the alias is a
  single string built from both maps, so moving one would render it half in
  each language.

Was in here, and is not any more
--------------------------------
The `agent.*` keys — the AI agent's "conversation not found", "forbidden",
"unavailable" and rate-limit messages — lived here until `main` reverted
ABF-122 (the agent conversation schema collided). Their only two callers,
`services/agent_service.py` and `dependencies.rate_limit_chat`, went with it,
and `test_i18n_catalogue.py::test_every_key_in_the_catalogue_is_used` is what
made leaving them behind impossible. When ABF-122 lands again the agent's
messages come back as keys, not as the Hebrew literals they were before —
`test_no_message_is_raised_in_hebrew` walks the whole of `app/`, so the
returning module is held to this rule the day it arrives.

`agent.rate_limited` was also the catalogue's only entry with a `{placeholder}`.
`TestCatalogue::test_placeholders_match_across_languages` now passes over an
empty set and stays for the next one; the rendering itself is still exercised,
against a catalogue entry the test defines, by
`test_i18n.py::TestTranslate::test_placeholders_are_filled`.
"""

from typing import Final

#: Language codes this API can answer in. Plain strings rather than the
#: `Language` enum so this module stays free of imports — `i18n.Language`
#: is a StrEnum, so it indexes these dicts directly.
HEBREW: Final = "he"
ENGLISH: Final = "en"

#: Every message the API can return, keyed by `<domain>.<message>`.
#:
#: The Hebrew side is the text that shipped before ABF-137, character for
#: character — including where it ends without a full stop. That is what lets
#: the existing suite assert on these strings unchanged, and the English side
#: mirrors the source's punctuation rather than tidying it.
MESSAGES: Final[dict[str, dict[str, str]]] = {
    # -- Authentication and registration ---------------------------------
    "auth.registered": {
        HEBREW: "נרשמת בהצלחה. בדוק את המייל לקוד OTP.",
        ENGLISH: "You are registered. Check your email for the verification code.",
    },
    "auth.otp_verified": {
        HEBREW: "אימות הצליח. הבקשה שלך ממתינה לאישור מנהלים.",
        ENGLISH: "Verified. Your request is waiting for administrator approval.",
    },
    "auth.otp_resent": {
        HEBREW: "קוד אימות נשלח מחדש",
        ENGLISH: "A new verification code has been sent",
    },
    "auth.google_linked": {
        HEBREW: "חשבון Google קושר בהצלחה.",
        ENGLISH: "Your Google account has been linked.",
    },
    "auth.email_taken": {
        HEBREW: "כתובת המייל כבר רשומה במערכת",
        ENGLISH: "That email address is already registered",
    },
    "auth.invalid_details": {
        HEBREW: "הפרטים שהוזנו שגויים",
        ENGLISH: "The details you entered are incorrect",
    },
    "auth.otp_expired": {
        HEBREW: "קוד האימות פג תוקף",
        ENGLISH: "The verification code has expired",
    },
    "auth.account_suspended": {
        HEBREW: "החשבון מושעה זמנית. נסה שוב מאוחר יותר.",
        ENGLISH: "This account is temporarily suspended. Please try again later.",
    },
    "auth.account_inactive": {
        HEBREW: "החשבון אינו פעיל. פנה/י למנהל.",
        ENGLISH: "This account is not active. Please contact an administrator.",
    },
    "auth.login_failed": {
        HEBREW: "אימות נכשל. בדוק/י מייל וסיסמה.",
        ENGLISH: "Sign-in failed. Check your email and password.",
    },
    "auth.google_failed": {
        HEBREW: "אימות Google נכשל. נסה/י שוב.",
        ENGLISH: "Google sign-in failed. Please try again.",
    },
    "auth.google_no_account": {
        HEBREW: "אין חשבון מקושר למייל זה. יש להירשם תחילה.",
        ENGLISH: "No account is linked to this email address. Please register first.",
    },
    "auth.google_email_linked_elsewhere": {
        HEBREW: "כתובת המייל מקושרת לחשבון Google אחר.",
        ENGLISH: "This email address is linked to a different Google account.",
    },
    "auth.google_already_linked": {
        HEBREW: "חשבון Google זה כבר מקושר למשתמש אחר.",
        ENGLISH: "This Google account is already linked to another user.",
    },
    "auth.invalid_refresh_token": {
        HEBREW: "טוקן רענון לא תקין.",
        ENGLISH: "Invalid refresh token.",
    },
    "auth.otp_send_failed": {
        HEBREW: "לא ניתן לשלוח קוד אימות",
        ENGLISH: "The verification code could not be sent",
    },
    # -- Members, registrations, the admin roster ------------------------
    "users.account_inactive": {
        HEBREW: "החשבון אינו פעיל.",
        ENGLISH: "This account is not active.",
    },
    "users.not_found": {
        HEBREW: "משתמש לא נמצא",
        ENGLISH: "User not found",
    },
    "users.registration_not_pending": {
        HEBREW: "ההרשמה אינה ממתינה לאישור",
        ENGLISH: "This registration is not awaiting approval",
    },
    "users.already_approved": {
        HEBREW: "לא ניתן לאשר את אותה הרשמה פעמיים",
        ENGLISH: "The same registration cannot be approved twice",
    },
    "users.suspend_members_only": {
        HEBREW: "ניתן להשעות רק משתמשים רגילים",
        ENGLISH: "Only regular members can be suspended",
    },
    "users.suspend_active_only": {
        HEBREW: "ניתן להשעות רק משתמש פעיל",
        ENGLISH: "Only an active member can be suspended",
    },
    "users.professionals_only": {
        HEBREW: "ניתן לערוך אנשי מקצוע בלבד",
        ENGLISH: "Only professionals can be edited",
    },
    "users.moderators_only": {
        HEBREW: "ניתן לערוך ממונים בלבד",
        ENGLISH: "Only moderators can be edited",
    },
    "users.moderator_already_removed": {
        HEBREW: "הממונה כבר הוסר מהמערכת",
        ENGLISH: "This moderator has already been removed",
    },
    "users.already_deleted": {
        HEBREW: "החשבון כבר נמחק",
        ENGLISH: "This account has already been deleted",
    },
    # -- Community forum --------------------------------------------------
    "forum.access_forbidden": {
        HEBREW: "אין לך הרשאה לגשת לפורום הקהילתי.",
        ENGLISH: "You do not have permission to access the community forum.",
    },
    "forum.post_not_found": {
        HEBREW: "ההודעה לא נמצאה.",
        ENGLISH: "The post was not found.",
    },
    "forum.post_view_forbidden": {
        HEBREW: "אין לך הרשאה לצפות בהודעה זו.",
        ENGLISH: "You do not have permission to view this post.",
    },
    "forum.post_delete_forbidden": {
        HEBREW: "אין לך הרשאה למחוק הודעה זו.",
        ENGLISH: "You do not have permission to delete this post.",
    },
    "forum.post_requires_active_account": {
        HEBREW: "רק משתמש פעיל יכול לפרסם הודעה.",
        ENGLISH: "Only an active member can publish a post.",
    },
    "forum.broadcast_admin_only": {
        HEBREW: "רק מנהל יכול לפרסם הודעה לכלל המשתמשים.",
        ENGLISH: "Only an administrator can publish a post to all members.",
    },
    "forum.post_group_forbidden": {
        HEBREW: "לא ניתן לפרסם הודעה לקבוצה שאינה שלך.",
        ENGLISH: "You cannot publish a post to a group other than your own.",
    },
    "forum.post_sector_forbidden": {
        HEBREW: "לא ניתן לפרסם הודעה למגזר שאינו שלך.",
        ENGLISH: "You cannot publish a post to a sector other than your own.",
    },
    "forum.post_edit_author_only": {
        HEBREW: "רק המחבר יכול לערוך הודעה זו.",
        ENGLISH: "Only the author can edit this post.",
    },
    # -- Reports ----------------------------------------------------------
    "reports.target_type_unsupported": {
        HEBREW: "סוג תוכן זה אינו נתמך לדיווח כרגע.",
        ENGLISH: "This content type cannot be reported yet.",
    },
    "reports.already_reported": {
        HEBREW: "כבר דיווחת על תוכן זה.",
        ENGLISH: "You have already reported this content.",
    },
    "reports.not_found": {
        HEBREW: "הדיווח לא נמצא.",
        ENGLISH: "The report was not found.",
    },
    "reports.target_not_found": {
        HEBREW: "התוכן המדווח לא נמצא.",
        ENGLISH: "The reported content was not found.",
    },
    "reports.view_forbidden": {
        HEBREW: "אין הרשאה לצפות בדיווח זה.",
        ENGLISH: "You do not have permission to view this report.",
    },
    "reports.payload_mismatch": {
        HEBREW: "נתוני הדיווח אינם תואמים את ההודעה המבוקשת.",
        ENGLISH: "The report details do not match the requested post.",
    },
    "reports.already_handled": {
        HEBREW: "הדיווח כבר טופל.",
        ENGLISH: "This report has already been handled.",
    },
    "reports.user_outside_your_cells": {
        HEBREW: "המשתמש אינו בתא שבאחריותך.",
        ENGLISH: "This member is not in a cell you are responsible for.",
    },
    # -- Professional Q&A -------------------------------------------------
    "professionals.query_not_found": {
        HEBREW: "השאלה לא נמצאה.",
        ENGLISH: "The question was not found.",
    },
    "professionals.answer_forbidden": {
        HEBREW: "אין לך הרשאה לענות על שאלה זו.",
        ENGLISH: "You do not have permission to answer this question.",
    },
    "professionals.query_already_answered": {
        HEBREW: "השאלה כבר נענתה.",
        ENGLISH: "This question has already been answered.",
    },
    # -- Likes ------------------------------------------------------------
    "likes.query_view_forbidden": {
        HEBREW: "אין לך הרשאה לצפות בשאלה זו.",
        ENGLISH: "You do not have permission to view this question.",
    },
    "likes.target_type_unsupported": {
        HEBREW: "סוג תוכן זה אינו נתמך ללייק כרגע.",
        ENGLISH: "This content type cannot be liked yet.",
    },
    "likes.answered_only": {
        HEBREW: "ניתן לסמן לייק רק לשאלה שנענתה.",
        ENGLISH: "Only a question that has been answered can be liked.",
    },
    # -- Cross-cutting ----------------------------------------------------
    "errors.unauthenticated": {
        HEBREW: "לא ניתן לאמת את הזהות. יש להתחבר מחדש.",
        ENGLISH: "Your identity could not be verified. Please sign in again.",
    },
    "errors.forbidden": {
        HEBREW: "אין לך הרשאה לבצע פעולה זו.",
        ENGLISH: "You do not have permission to perform this action.",
    },
    # -- Pydantic field validators (reach the client through 422) ---------
    "validation.phone_digits_only": {
        HEBREW: "מספר הטלפון חייב להכיל ספרות בלבד",
        ENGLISH: "The phone number must contain digits only",
    },
    "validation.field_not_clearable": {
        HEBREW: "לא ניתן לרוקן שדה זה. יש להשמיטו כדי להשאירו ללא שינוי.",
        ENGLISH: "This field cannot be cleared. Omit it to leave it unchanged.",
    },
    "validation.decision_required": {
        HEBREW: "יש לבחור החלטה: מוצדק או שגוי",
        ENGLISH: "Choose a decision: justified or mistaken",
    },
    "validation.review_note_too_short": {
        HEBREW: "הערת המבקר חייבת לכלול לפחות 5 תווים",
        ENGLISH: "The reviewer's note must be at least 5 characters long",
    },
}
