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

export interface ReportDecideRequest {
  decision: ReportDecision;
  note?: string;
}

export interface ReportList {
  items: Report[];
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
