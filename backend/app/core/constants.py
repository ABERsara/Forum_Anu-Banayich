"""
Domain enums for the "Anu Banayich" platform.

Every enum here has a matching TypeScript equivalent in:
frontend/src/app/core/constants/index.ts

When you add a value here, add it there too!
"""

import enum


class UserRole(enum.StrEnum):
    """System-level role – controls which pages/actions are allowed."""

    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"
    PROFESSIONAL = "professional"


class UserType(enum.StrEnum):
    """Only for USER role – which bereavement group the person belongs to."""

    WIDOWER = "widower"  # אלמן
    WIDOW = "widow"  # אלמנה
    ORPHAN_MALE = "orphan_male"  # יתום
    ORPHAN_FEMALE = "orphan_female"  # יתומה


class Sector(enum.StrEnum):
    """Religious/cultural sector – second axis of the content filter matrix."""

    HASIDIC = "hasidic"  # חסידי
    LITVISH = "litvish"  # ליטאי
    SEPHARDIC = "sephardic"  # ספרדי
    GENERAL = "general"  # כללי


class AccountStatus(enum.StrEnum):
    """Registration lifecycle states."""

    PENDING_OTP = "pending_otp"  # ממתין לאימות מייל/טלפון
    PENDING_APPROVAL = "pending_approval"  # ממתין לאישור 2 מנהלים
    PARTIALLY_APPROVED = "partially_approved"  # מנהל אחד אישר, ממתין לשני
    ACTIVE = "active"  # פעיל – גישה מלאה
    REJECTED = "rejected"  # נדחה
    SUSPENDED = "suspended"  # מושעה זמנית
    CANCELLED = "cancelled"  # בוטל (מחיקה עצמית / GDPR)


class GroupVisibility(enum.StrEnum):
    """
    Who can see a piece of content – group axis.
    Used on ForumPost, ProfessionalQuery, DirectMessage.
    """

    WIDOWERS = "widower"  # אלמנים בלבד
    WIDOWS = "widow"  # אלמנות בלבד
    ORPHANS_MALE = "orphan_male"  # יתומים בלבד
    ORPHANS_FEMALE = "orphan_female"  # יתומות בלבד
    ALL = "all"  # כולם


class SectorVisibility(enum.StrEnum):
    """
    Who can see a piece of content – sector axis.
    Used on ForumPost, ProfessionalQuery, DirectMessage.
    """

    HASIDIC = "hasidic"
    LITVISH = "litvish"
    SEPHARDIC = "sephardic"
    GENERAL = "general"
    ALL = "all"  # כל המגזרים


class PostStatus(enum.StrEnum):
    """Moderation state of a forum post."""

    VISIBLE = "visible"  # גלוי
    HIDDEN = "hidden"  # מוסתר (הוסתר אוטומטית אחרי 2 דיווחים)
    DELETED = "deleted"  # מחוק (מנהל/מבקר מחק)


class ProfessionalDomain(enum.StrEnum):
    """Area of expertise for Professional users."""

    LAWYER = "lawyer"  # עו"ד
    ACCOUNTANT = "accountant"  # רואה חשבון
    PSYCHOLOGIST = "psychologist"  # פסיכולוג
    FINANCIAL_ADVISOR = "financial_advisor"  # יועץ כלכלי
    RABBI = "rabbi"  # רב/דיין
    MEDICINE = "medicine"  # רפואה
    SOCIAL_WORKER = "social_worker"  # סוציאל וורקר
    OTHER = "other"  # אחר


class QueryStatus(enum.StrEnum):
    """Life-cycle of a professional query."""

    OPEN = "open"  # פתוח – טרם נענה
    ANSWERED = "answered"  # נענה
    CLOSED = "closed"  # סגור


class ReportReason(enum.StrEnum):
    """Why the user reported a piece of content."""

    HARASSMENT = "harassment"  # הטרדה
    OFFENSIVE = "offensive"  # תוכן פוגעני
    SPAM = "spam"  # ספאם
    OTHER = "other"  # אחר


class ReportTargetType(enum.StrEnum):
    """What type of content was reported."""

    FORUM_POST = "forum_post"  # הודעת פורום
    DIRECT_MESSAGE = "direct_message"  # הודעה פרטית
    PROFESSIONAL_QUERY = "professional_query"  # שאלה מקצועית


class ReportDecision(enum.StrEnum):
    """Moderator's decision on a report."""

    PENDING = "pending"  # ממתין לטיפול
    INVALID = "invalid"  # שגוי – הודעה הושבה
    VALID = "valid"  # מוצדק – הודעה נמחקה


class DocumentType(enum.StrEnum):
    """Types of documents uploaded during registration."""

    DEATH_CERTIFICATE = "death_certificate"  # תעודת פטירה
    SELFIE = "selfie"  # תמונת פנים (selfie)
    ID_CARD = "id_card"  # ת"ז
    PASSPORT = "passport"  # דרכון


class AuditAction(enum.StrEnum):
    """Sensitive admin/moderator actions that must be logged."""

    USER_APPROVED = "user_approved"
    USER_PARTIALLY_APPROVED = "user_partially_approved"
    USER_REJECTED = "user_rejected"
    USER_SUSPENDED = "user_suspended"
    USER_CANCELLED = "user_cancelled"
    POST_DELETED = "post_deleted"
    BROADCAST_SENT = "broadcast_sent"
    REPORT_DECIDED = "report_decided"
    PROFESSIONAL_ADDED = "professional_added"
    PROFESSIONAL_UPDATED = "professional_updated"
    MODERATOR_ASSIGNED = "moderator_assigned"
    DATA_EXPORTED = "data_exported"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"


# ---------------------------------------------------------------------------
# Human-readable Hebrew labels (useful for emails and admin UI)
# ---------------------------------------------------------------------------

USER_TYPE_LABELS: dict[UserType, str] = {
    UserType.WIDOWER: "אלמן",
    UserType.WIDOW: "אלמנה",
    UserType.ORPHAN_MALE: "יתום",
    UserType.ORPHAN_FEMALE: "יתומה",
}

SECTOR_LABELS: dict[Sector, str] = {
    Sector.HASIDIC: "חסידי",
    Sector.LITVISH: "ליטאי",
    Sector.SEPHARDIC: "ספרדי",
    Sector.GENERAL: "כללי",
}

PROFESSIONAL_DOMAIN_LABELS: dict[ProfessionalDomain, str] = {
    ProfessionalDomain.LAWYER: 'עו"ד',
    ProfessionalDomain.ACCOUNTANT: "רואה חשבון",
    ProfessionalDomain.PSYCHOLOGIST: "פסיכולוג",
    ProfessionalDomain.FINANCIAL_ADVISOR: "יועץ כלכלי",
    ProfessionalDomain.RABBI: "רב/דיין",
    ProfessionalDomain.MEDICINE: "רפואה",
    ProfessionalDomain.SOCIAL_WORKER: "סוציאל וורקר",
    ProfessionalDomain.OTHER: "אחר",
}

ACCOUNT_STATUS_LABELS: dict[AccountStatus, str] = {
    AccountStatus.PENDING_OTP: "ממתין לאימות",
    AccountStatus.PENDING_APPROVAL: "ממתין לאישור מנהלים",
    AccountStatus.PARTIALLY_APPROVED: "אושר חלקית",
    AccountStatus.ACTIVE: "פעיל",
    AccountStatus.REJECTED: "נדחה",
    AccountStatus.SUSPENDED: "מושעה",
    AccountStatus.CANCELLED: "בוטל",
}
