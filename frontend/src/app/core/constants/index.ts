/**
 * Domain constants for the "Anu Banayich" platform.
 *
 * ⚠️  These MUST stay in sync with backend/app/core/constants.py
 *     If you add a value here, add it there too (and vice versa).
 */

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

export enum UserRole {
  USER = 'user',
  ADMIN = 'admin',
  MODERATOR = 'moderator',
  PROFESSIONAL = 'professional',
}

// ---------------------------------------------------------------------------
// User type – only for USER role
// ---------------------------------------------------------------------------

export enum UserType {
  WIDOWER = 'widower', // אלמן
  WIDOW = 'widow', // אלמנה
  ORPHAN_MALE = 'orphan_male', // יתום
  ORPHAN_FEMALE = 'orphan_female', // יתומה
}

export const USER_TYPE_LABELS: Record<UserType, string> = {
  [UserType.WIDOWER]: 'אלמן',
  [UserType.WIDOW]: 'אלמנה',
  [UserType.ORPHAN_MALE]: 'יתום',
  [UserType.ORPHAN_FEMALE]: 'יתומה',
};

// ---------------------------------------------------------------------------
// Sector
// ---------------------------------------------------------------------------

export enum Sector {
  HASIDIC = 'hasidic', // חסידי
  LITVISH = 'litvish', // ליטאי
  SEPHARDIC = 'sephardic', // ספרדי
  GENERAL = 'general', // כללי
}

export const SECTOR_LABELS: Record<Sector, string> = {
  [Sector.HASIDIC]: 'חסידי',
  [Sector.LITVISH]: 'ליטאי',
  [Sector.SEPHARDIC]: 'ספרדי',
  [Sector.GENERAL]: 'כללי',
};

// ---------------------------------------------------------------------------
// Account status
// ---------------------------------------------------------------------------

export enum AccountStatus {
  PENDING_OTP = 'pending_otp',
  PENDING_APPROVAL = 'pending_approval',
  PARTIALLY_APPROVED = 'partially_approved',
  ACTIVE = 'active',
  REJECTED = 'rejected',
  SUSPENDED = 'suspended',
  CANCELLED = 'cancelled',
}

export const ACCOUNT_STATUS_LABELS: Record<AccountStatus, string> = {
  [AccountStatus.PENDING_OTP]: 'ממתין לאימות',
  [AccountStatus.PENDING_APPROVAL]: 'ממתין לאישור מנהלים',
  [AccountStatus.PARTIALLY_APPROVED]: 'אושר חלקית',
  [AccountStatus.ACTIVE]: 'פעיל',
  [AccountStatus.REJECTED]: 'נדחה',
  [AccountStatus.SUSPENDED]: 'מושעה',
  [AccountStatus.CANCELLED]: 'בוטל',
};

// ---------------------------------------------------------------------------
// Content visibility
// ---------------------------------------------------------------------------

export enum GroupVisibility {
  WIDOWERS = 'widower',
  WIDOWS = 'widow',
  ORPHANS_MALE = 'orphan_male',
  ORPHANS_FEMALE = 'orphan_female',
  ALL = 'all',
}

export enum SectorVisibility {
  HASIDIC = 'hasidic',
  LITVISH = 'litvish',
  SEPHARDIC = 'sephardic',
  GENERAL = 'general',
  ALL = 'all',
}

export const GROUP_VISIBILITY_LABELS: Record<GroupVisibility, string> = {
  [GroupVisibility.WIDOWERS]: 'אלמנים',
  [GroupVisibility.WIDOWS]: 'אלמנות',
  [GroupVisibility.ORPHANS_MALE]: 'יתומים',
  [GroupVisibility.ORPHANS_FEMALE]: 'יתומות',
  [GroupVisibility.ALL]: 'כולם',
};

export const SECTOR_VISIBILITY_LABELS: Record<SectorVisibility, string> = {
  [SectorVisibility.HASIDIC]: 'חסידי',
  [SectorVisibility.LITVISH]: 'ליטאי',
  [SectorVisibility.SEPHARDIC]: 'ספרדי',
  [SectorVisibility.GENERAL]: 'כללי',
  [SectorVisibility.ALL]: 'כל המגזרים',
};

// ---------------------------------------------------------------------------
// Forum post status
// ---------------------------------------------------------------------------

export enum PostStatus {
  VISIBLE = 'visible',
  HIDDEN = 'hidden',
  DELETED = 'deleted',
}

// ---------------------------------------------------------------------------
// Professional domains
// ---------------------------------------------------------------------------

export enum ProfessionalDomain {
  LAWYER = 'lawyer',
  ACCOUNTANT = 'accountant',
  PSYCHOLOGIST = 'psychologist',
  FINANCIAL_ADVISOR = 'financial_advisor',
  RABBI = 'rabbi',
  MEDICINE = 'medicine',
  SOCIAL_WORKER = 'social_worker',
  OTHER = 'other',
}

export const PROFESSIONAL_DOMAIN_LABELS: Record<ProfessionalDomain, string> = {
  [ProfessionalDomain.LAWYER]: 'עו"ד',
  [ProfessionalDomain.ACCOUNTANT]: 'רואה חשבון',
  [ProfessionalDomain.PSYCHOLOGIST]: 'פסיכולוג',
  [ProfessionalDomain.FINANCIAL_ADVISOR]: 'יועץ כלכלי',
  [ProfessionalDomain.RABBI]: 'רב/דיין',
  [ProfessionalDomain.MEDICINE]: 'רפואה',
  [ProfessionalDomain.SOCIAL_WORKER]: 'סוציאל וורקר',
  [ProfessionalDomain.OTHER]: 'אחר',
};

// ---------------------------------------------------------------------------
// Query (professional question) status
// ---------------------------------------------------------------------------

export enum QueryStatus {
  OPEN = 'open',
  ANSWERED = 'answered',
  CLOSED = 'closed',
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export enum ReportReason {
  HARASSMENT = 'harassment',
  OFFENSIVE = 'offensive',
  SPAM = 'spam',
  OTHER = 'other',
}

export const REPORT_REASON_LABELS: Record<ReportReason, string> = {
  [ReportReason.HARASSMENT]: 'הטרדה',
  [ReportReason.OFFENSIVE]: 'תוכן פוגעני',
  [ReportReason.SPAM]: 'ספאם',
  [ReportReason.OTHER]: 'אחר',
};

export enum ReportTargetType {
  FORUM_POST = 'forum_post',
  DIRECT_MESSAGE = 'direct_message',
  PROFESSIONAL_QUERY = 'professional_query',
}

export enum ReportDecision {
  PENDING = 'pending',
  INVALID = 'invalid',
  VALID = 'valid',
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export enum DocumentType {
  DEATH_CERTIFICATE = 'death_certificate',
  SELFIE = 'selfie',
  ID_CARD = 'id_card',
  PASSPORT = 'passport',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Returns true if the current user can post/read in the given visibility scope. */
export function userMatchesGroupVisibility(
  userType: UserType,
  visibility: GroupVisibility,
): boolean {
  if (visibility === GroupVisibility.ALL) return true;
  return (visibility as string) === (userType as string);
}
