/**
 * TypeScript interfaces matching the backend Pydantic schemas.
 *
 * ⚠️  These must stay in sync with backend/app/schemas/*.py
 *
 * Naming convention:
 *   - Use the same names as the Pydantic schemas (PascalCase)
 *   - API responses → interface (not class)
 *   - API request bodies → also interfaces
 */

import {
  AccountStatus,
  DocumentType,
  GroupVisibility,
  ProfessionalDomain,
  QueryStatus,
  ReportDecision,
  ReportReason,
  ReportTargetType,
  Sector,
  SectorVisibility,
  PostStatus,
  UserRole,
  UserType,
} from '../constants';

// ---------------------------------------------------------------------------
// User
// ---------------------------------------------------------------------------

/** Minimal user info shown to others (name only, no PII). */
export interface UserPublic {
  id: string;
  first_name: string;
  last_name: string;
}

/** Full profile for the logged-in user themselves. */
export interface UserProfile {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  role: UserRole;
  user_type: UserType | null;
  sector: Sector | null;
  birth_date: string | null; // ISO date string "YYYY-MM-DD"
  account_status: AccountStatus;
  created_at: string; // ISO datetime
}

/** What admin sees when reviewing a registration. */
export interface UserAdminView extends UserProfile {
  phone: string | null;
  id_number: string | null;
  first_approver_id: string | null;
  second_approver_id: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
}

/**
 * One document filed with a registration, as the reviewing admin sees it —
 * metadata only.
 *
 * There is no link here on purpose: the files are opened through time-limited
 * presigned URLs (SPEC §9.1), which are still in the backlog, and the storage
 * path behind them is never handed to the client.
 */
export interface DocumentAdminView {
  id: string;
  doc_type: DocumentType;
  /** ISO date "YYYY-MM-DD". Null for documents that do not expire. */
  expires_on: string | null;
  uploaded_at: string; // ISO datetime
}

/**
 * One registration as the deciding admin reads it: everything the queue row
 * carries, plus the documents that came with it, oldest upload first.
 */
export interface RegistrationDetail extends UserAdminView {
  documents: DocumentAdminView[];
}

/** Admin rejects a pending registration. */
export interface RegistrationRejectRequest {
  reason: string;
}

/** Professional as shown in the professionals catalog. */
export interface ProfessionalProfile {
  id: string;
  first_name: string;
  last_name: string;
  professional_domain: ProfessionalDomain;
  professional_description: string | null;
}

/**
 * Professional as the admin managing the catalog sees them — unlike
 * ProfessionalProfile this carries contact details and the routing fields
 * (which groups and sectors they serve, and whether they are listed at all).
 */
export interface ProfessionalAdminView {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  role: UserRole;
  account_status: AccountStatus;
  professional_domain: ProfessionalDomain | null;
  professional_groups: GroupVisibility[];
  professional_sectors: SectorVisibility[];
  professional_description: string | null;
  is_active_professional: boolean;
  created_at: string;
}

/** Admin adds a professional to the catalog. */
export interface ProfessionalCreateRequest {
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  professional_domain: ProfessionalDomain;
  professional_groups: GroupVisibility[];
  professional_sectors: SectorVisibility[];
  professional_description: string | null;
  is_active_professional: boolean;
}

/**
 * Admin edits a professional. Partial by design: an omitted key is left
 * untouched, so `{ is_active_professional: false }` only flips the listing.
 */
export interface ProfessionalUpdateRequest {
  professional_domain?: ProfessionalDomain;
  professional_groups?: GroupVisibility[];
  professional_sectors?: SectorVisibility[];
  professional_description?: string | null;
  is_active_professional?: boolean;
}

/** Admin suspends an active user for N hours. */
export interface SuspendUserRequest {
  hours: number;
  reason: string;
}

// ---------------------------------------------------------------------------
// Moderator roster (admin side)
// ---------------------------------------------------------------------------

/**
 * One cell of the group×sector matrix a moderator oversees, e.g. widows in
 * the Sephardic sector.
 *
 * Both axes are the concrete enums, never the "all" wildcard the content
 * visibility enums carry: a moderator answers for named cells, so "every
 * cell" is expressed by ticking them.
 */
export interface ModeratorCell {
  group: UserType;
  sector: Sector;
}

/**
 * A moderator as the admin managing the roster sees them: who they are, the
 * cells they were assigned, and where their alerts are sent.
 */
export interface ModeratorAdminView {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  role: UserRole;
  account_status: AccountStatus;
  moderator_cells: ModeratorCell[];
  /** Where report alerts go. Null means they go to `email`. */
  alert_email: string | null;
  created_at: string;
}

/** Admin appoints a moderator over the given cells. */
export interface ModeratorCreateRequest {
  first_name: string;
  last_name: string;
  email: string;
  moderator_cells: ModeratorCell[];
  alert_email: string | null;
}

/**
 * Admin edits a moderator. Partial by design: an omitted key is left
 * untouched, so `{ alert_email: 'x@y.z' }` only moves where alerts are sent.
 * An explicit `null` alert_email clears it; the cell list cannot be emptied.
 */
export interface ModeratorUpdateRequest {
  moderator_cells?: ModeratorCell[];
  alert_email?: string | null;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface RegisterRequest {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  birth_date: string; // "YYYY-MM-DD"
  user_type: UserType;
  sector: Sector;
  id_number: string;
  password: string;
}

export interface OtpVerifyRequest {
  email: string;
  otp_code: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
}

/** Body for POST /auth/google and POST /auth/google/link. */
export interface GoogleAuthRequest {
  id_token: string;
}

// ---------------------------------------------------------------------------
// Forum
// ---------------------------------------------------------------------------

export interface ForumPostCreate {
  title: string;
  content: string;
  group_visibility: GroupVisibility;
  sector_visibility: SectorVisibility;
}

export interface ForumPostUpdate {
  title?: string;
  content?: string;
}

export interface BroadcastCreate {
  title: string;
  content: string;
}

export interface ForumPost {
  id: string;
  title: string;
  content: string;
  group_visibility: GroupVisibility;
  sector_visibility: SectorVisibility;
  status: PostStatus;
  report_count: number;
  author: UserPublic;
  attachment_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface ForumPostList {
  items: ForumPost[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// Direct messages
// ---------------------------------------------------------------------------

export interface DirectMessageCreate {
  recipient_id: string;
  content: string;
}

export interface DirectMessage {
  id: string;
  sender: UserPublic;
  recipient: UserPublic;
  content: string;
  is_read: boolean;
  created_at: string;
}

export interface ConversationSummary {
  other_user: UserPublic;
  last_message_preview: string;
  last_message_at: string;
  unread_count: number;
}

export interface ConversationList {
  items: ConversationSummary[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// Professional queries
// ---------------------------------------------------------------------------

export interface ProfessionalQueryCreate {
  content: string;
  is_public: boolean;
  show_real_name: boolean;
  professional_id?: string;
  domain?: ProfessionalDomain;
}

export interface ProfessionalQuery {
  id: string;
  content: string;
  answer: string | null;
  is_public: boolean;
  status: QueryStatus;
  is_featured: boolean;
  domain: ProfessionalDomain | null;
  professional: ProfessionalProfile | null;
  asker_alias: string;
  asker: UserPublic | null;
  created_at: string;
  answered_at: string | null;
}

export interface PublicQA {
  id: string;
  content: string;
  answer: string;
  domain: ProfessionalDomain | null;
  is_featured: boolean;
  answered_at: string | null;
  like_count: number;
  liked_by_me: boolean;
}

// ---------------------------------------------------------------------------
// Likes
// ---------------------------------------------------------------------------

export interface LikeResponse {
  liked: boolean;
  like_count: number;
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export interface ReportCreate {
  target_type: ReportTargetType;
  target_id: string;
  reason: ReportReason;
  description?: string;
}

export interface Report {
  id: string;
  reporter_id: string;
  reported_user_id: string;
  target_type: ReportTargetType;
  target_id: string;
  reason: ReportReason;
  description: string | null;
  decision: ReportDecision;
  moderator_id: string | null;
  moderator_note: string | null;
  decided_at: string | null;
  created_at: string;
}

/** A report enriched with the reported content, returned by moderator views. */
export interface ReportWithContent extends Report {
  content_title: string;
  content_text: string;
  content_status: PostStatus;
  report_count: number;
}

export interface ReportDecideRequest {
  decision: ReportDecision;
  note?: string;
}

export interface ReportList {
  items: ReportWithContent[];
  total: number;
  pending_count: number;
}

// ---------------------------------------------------------------------------
// Pagination helper
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// Auth state (stored in AuthService)
// ---------------------------------------------------------------------------

export interface AuthState {
  user: UserProfile | null;
  isLoggedIn: boolean;
  isUser: boolean;
  isAdmin: boolean;
  isModerator: boolean;
  isProfessional: boolean;
}
