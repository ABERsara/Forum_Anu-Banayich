/**
 * Domain constants for the "Anu Banayich" platform.
 *
 * ⚠️  These MUST stay in sync with backend/app/core/constants.py
 *     If you add a value here, add it there too (and vice versa).
 *
 * ⚠️  Every `*_LABELS` map here holds i18n *keys*, never display text.
 *     See {@link LabelKey} for how to render one.
 */

/**
 * An i18n key into `public/i18n/{he,en}.json` — not text to show the user.
 *
 * The `*_LABELS` maps below are the platform's shared vocabulary: one map per
 * enum, imported by a dozen feature modules. Holding keys rather than Hebrew
 * strings is what lets those modules be translated one at a time without any
 * of them editing this file, and what keeps one label from being translated
 * twice, differently, in two of them.
 *
 * Resolve a key before it reaches the screen — in a template with the pipe,
 * which also re-renders it on a language switch:
 *
 * ```html
 * {{ sectorLabels[user.sector] | transloco }}
 * ```
 *
 * or, only where TypeScript has to assemble the string itself, with
 * `LabelService` (`core/i18n/label.service.ts`):
 *
 * ```ts
 * this.labels.label(SECTOR_LABELS[user.sector]);
 * ```
 */
export type LabelKey = string;

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

/** The person, in the singular. Contrast GROUP_VISIBILITY_LABELS. */
export const USER_TYPE_LABELS: Record<UserType, LabelKey> = {
  [UserType.WIDOWER]: 'constants.user_type.widower',
  [UserType.WIDOW]: 'constants.user_type.widow',
  [UserType.ORPHAN_MALE]: 'constants.user_type.orphan_male',
  [UserType.ORPHAN_FEMALE]: 'constants.user_type.orphan_female',
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

export const SECTOR_LABELS: Record<Sector, LabelKey> = {
  [Sector.HASIDIC]: 'constants.sector.hasidic',
  [Sector.LITVISH]: 'constants.sector.litvish',
  [Sector.SEPHARDIC]: 'constants.sector.sephardic',
  [Sector.GENERAL]: 'constants.sector.general',
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

export const ACCOUNT_STATUS_LABELS: Record<AccountStatus, LabelKey> = {
  [AccountStatus.PENDING_OTP]: 'constants.account_status.pending_otp',
  [AccountStatus.PENDING_APPROVAL]: 'constants.account_status.pending_approval',
  [AccountStatus.PARTIALLY_APPROVED]: 'constants.account_status.partially_approved',
  [AccountStatus.ACTIVE]: 'constants.account_status.active',
  [AccountStatus.REJECTED]: 'constants.account_status.rejected',
  [AccountStatus.SUSPENDED]: 'constants.account_status.suspended',
  [AccountStatus.CANCELLED]: 'constants.account_status.cancelled',
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

/**
 * The audience, in the plural. A post is addressed to a population, not to a
 * person, so these read differently from USER_TYPE_LABELS even though every
 * GroupVisibility value except ALL is also a UserType value.
 */
export const GROUP_VISIBILITY_LABELS: Record<GroupVisibility, LabelKey> = {
  [GroupVisibility.WIDOWERS]: 'constants.group_visibility.widower',
  [GroupVisibility.WIDOWS]: 'constants.group_visibility.widow',
  [GroupVisibility.ORPHANS_MALE]: 'constants.group_visibility.orphan_male',
  [GroupVisibility.ORPHANS_FEMALE]: 'constants.group_visibility.orphan_female',
  [GroupVisibility.ALL]: 'constants.group_visibility.all',
};

/**
 * A sector reads the same whether it names a person's sector or a post's
 * audience, so the four shared values deliberately point at the very keys
 * SECTOR_LABELS uses: one sector, one translation, no drift between the two
 * maps. Only ALL, which has no counterpart in Sector, needs a key of its own.
 */
export const SECTOR_VISIBILITY_LABELS: Record<SectorVisibility, LabelKey> = {
  [SectorVisibility.HASIDIC]: SECTOR_LABELS[Sector.HASIDIC],
  [SectorVisibility.LITVISH]: SECTOR_LABELS[Sector.LITVISH],
  [SectorVisibility.SEPHARDIC]: SECTOR_LABELS[Sector.SEPHARDIC],
  [SectorVisibility.GENERAL]: SECTOR_LABELS[Sector.GENERAL],
  [SectorVisibility.ALL]: 'constants.sector_visibility.all',
};

// ---------------------------------------------------------------------------
// Forum post status
// ---------------------------------------------------------------------------

export enum PostStatus {
  VISIBLE = 'visible',
  HIDDEN = 'hidden',
  DELETED = 'deleted',
}

export const POST_STATUS_LABELS: Record<PostStatus, LabelKey> = {
  [PostStatus.VISIBLE]: 'constants.post_status.visible',
  [PostStatus.HIDDEN]: 'constants.post_status.hidden',
  [PostStatus.DELETED]: 'constants.post_status.deleted',
};

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

export const PROFESSIONAL_DOMAIN_LABELS: Record<ProfessionalDomain, LabelKey> = {
  [ProfessionalDomain.LAWYER]: 'constants.professional_domain.lawyer',
  [ProfessionalDomain.ACCOUNTANT]: 'constants.professional_domain.accountant',
  [ProfessionalDomain.PSYCHOLOGIST]: 'constants.professional_domain.psychologist',
  [ProfessionalDomain.FINANCIAL_ADVISOR]: 'constants.professional_domain.financial_advisor',
  [ProfessionalDomain.RABBI]: 'constants.professional_domain.rabbi',
  [ProfessionalDomain.MEDICINE]: 'constants.professional_domain.medicine',
  [ProfessionalDomain.SOCIAL_WORKER]: 'constants.professional_domain.social_worker',
  [ProfessionalDomain.OTHER]: 'constants.professional_domain.other',
};

// ---------------------------------------------------------------------------
// Query (professional question) status
// ---------------------------------------------------------------------------

export enum QueryStatus {
  OPEN = 'open',
  ANSWERED = 'answered',
  CLOSED = 'closed',
}

export const QUERY_STATUS_LABELS: Record<QueryStatus, LabelKey> = {
  [QueryStatus.OPEN]: 'constants.query_status.open',
  [QueryStatus.ANSWERED]: 'constants.query_status.answered',
  [QueryStatus.CLOSED]: 'constants.query_status.closed',
};

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export enum ReportReason {
  HARASSMENT = 'harassment',
  OFFENSIVE = 'offensive',
  SPAM = 'spam',
  OTHER = 'other',
}

export const REPORT_REASON_LABELS: Record<ReportReason, LabelKey> = {
  [ReportReason.HARASSMENT]: 'constants.report_reason.harassment',
  [ReportReason.OFFENSIVE]: 'constants.report_reason.offensive',
  [ReportReason.SPAM]: 'constants.report_reason.spam',
  [ReportReason.OTHER]: 'constants.report_reason.other',
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
// Likes
// ---------------------------------------------------------------------------

export enum LikeTargetType {
  FORUM_POST = 'forum_post',
  PROFESSIONAL_QUERY = 'professional_query',
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

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, LabelKey> = {
  [DocumentType.DEATH_CERTIFICATE]: 'constants.document_type.death_certificate',
  [DocumentType.SELFIE]: 'constants.document_type.selfie',
  [DocumentType.ID_CARD]: 'constants.document_type.id_card',
  [DocumentType.PASSPORT]: 'constants.document_type.passport',
};

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
