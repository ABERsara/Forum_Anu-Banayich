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
  AgentMessageRole,
  AuditAction,
  AuditSortField,
  DocumentType,
  GroupVisibility,
  ProfessionalDomain,
  QueryStatus,
  ReportDecision,
  ReportReason,
  ReportTargetType,
  RestrictionType,
  Sector,
  SectorVisibility,
  SortDirection,
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

/** Admin or moderator suspends an active user for N hours. */
export interface SuspendUserRequest {
  hours: number;
  reason: string;
}

/**
 * One user's moderation history, as the moderator responsible for their cell
 * sees it (SPEC §7.3, "כרטיס משתמש").
 *
 * Deliberately without contact details: UserAdminView carries the email,
 * phone and ID number, and it is an admin view for exactly that reason.
 */
export interface UserModerationCard {
  id: string;
  first_name: string;
  last_name: string;
  user_type: UserType | null;
  sector: Sector | null;
  account_status: AccountStatus;

  /** Reports filed against this user; the rest of the total is still pending. */
  reports_against_total: number;
  reports_against_valid: number;
  reports_against_invalid: number;

  /** Reports this user filed about others. */
  reports_filed_total: number;
  false_reports_filed: number;

  is_suspended: boolean;
  suspended_until: string | null; // ISO datetime
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
  like_count: number;
  liked_by_me: boolean;
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
  /**
   * When the *recipient* opened the conversation; null until then. A
   * timestamp rather than a flag, because it is what the sender's own bubble
   * shows as a receipt — and a flag cannot say when.
   */
  read_at: string | null; // ISO datetime
  created_at: string;
  /**
   * Whether *this viewer* has already reported the message (ABF-112).
   *
   * Server-side rather than remembered on the screen, so the mark is still
   * there after a reload — and so the same message cannot be reported twice
   * by a client that forgot it had. Always false on a message the viewer
   * sent: only its recipient can report one.
   */
  reported_by_me: boolean;
  /**
   * A moderator upheld a report on this message (ABF-113).
   *
   * `content` is already empty when this is true — the server never
   * decrypts a hidden message — so this is what tells the screen to render
   * a placeholder instead of an empty bubble.
   */
  hidden: boolean;
}

/**
 * One page of a conversation, oldest first *within the page*.
 *
 * Paging runs backwards: the first request (no cursor) returns the newest
 * messages, and `next_cursor` walks towards the oldest. Feed it back as the
 * `before` option to get the page before this one; it is null exactly when
 * `has_more` is false.
 */
export interface ConversationMessagesPage {
  items: DirectMessage[];
  has_more: boolean;
  next_cursor: string | null;
}

/**
 * What a send comes back with: the stored message, and what enforcing the
 * conversation's storage cap (SPEC §5.3) cost.
 *
 * `pruned_message_ids` is normally empty, and names the deleted messages
 * rather than counting them: the cap skips anything under an open report, so
 * the oldest message on screen is not necessarily one of the ones that went.
 * `conversation_limit` is the server's current cap, so the notice can name
 * the real number instead of hardcoding a copy of a setting.
 */
export interface DirectMessageSendResult {
  message: DirectMessage;
  pruned_message_ids: string[];
  conversation_limit: number;
}

export interface ConversationSummary {
  other_user: UserPublic;
  last_message_preview: string;
  last_message_at: string;
  unread_count: number;
  /** A moderator upheld a report on the last message (ABF-113). last_message_preview is already empty when this is true. */
  hidden: boolean;
}

export interface ConversationList {
  items: ConversationSummary[];
  total: number;
  page: number;
  page_size: number;
}

/**
 * One message in a self-service export (SPEC §9.5, ABF-117). Ids, not nested
 * UserPublic objects: this is a personal-data export, not a conversation view.
 */
export interface DirectMessageExportItem {
  id: string;
  sender_id: string;
  recipient_id: string;
  content: string;
  sent_at: string; // ISO datetime
  read_at: string | null; // ISO datetime
}

/** GET /users/me/messages/export — every message the caller sent or received. */
export interface DirectMessageExportResult {
  items: DirectMessageExportItem[];
  total: number;
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
  domain: ProfessionalDomain | null;
  professional: ProfessionalProfile | null;
  asker_alias: string;
  asker: UserPublic | null;
  created_at: string;
  answered_at: string | null;
  like_count: number;
  liked_by_me: boolean;
}

export interface PublicQA {
  id: string;
  content: string;
  answer: string;
  domain: ProfessionalDomain | null;
  answered_at: string | null;
  like_count: number;
  liked_by_me: boolean;
  professional: ProfessionalProfile | null;
  asker_alias: string;
  asker: UserPublic | null;
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
  /** Null once the report has been anonymized — see §9.4. */
  reporter_id: string | null;
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

/**
 * A FORUM_POST report enriched with the reported post.
 *
 * A post is never hard-deleted today (only its status changes), so these
 * are populated on every row in practice — but the backend's own defensive
 * branch for a post that is somehow gone (moderator.py's
 * _to_reports_with_content()) sends this same target_type with all four
 * left out, so they stay optional here too rather than claim a guarantee
 * the backend doesn't actually make.
 */
export interface ForumPostReport extends Report {
  target_type: ReportTargetType.FORUM_POST;
  content_title?: string;
  content_text?: string;
  content_status?: PostStatus;
  report_count?: number;
}

/** A DIRECT_MESSAGE report enriched with the reported message. */
export interface DirectMessageReport extends Report {
  target_type: ReportTargetType.DIRECT_MESSAGE;
  /**
   * The decrypted message. Present only on the single report fetched by
   * `GET /moderator/reports/{id}` (an audited read, ABF-113, spec §9.3) —
   * never on a list row, and never (even there) once the report is
   * CLOSED_ACCOUNT_DELETED.
   */
  message_content?: string | null;
}

/**
 * A report enriched with the reported content, returned by moderator views.
 *
 * One shape for a pending/history list mixes both target types (SPEC §7.3),
 * so this is a discriminated union rather than one interface with optional
 * fields either target_type may leave unset: narrowing on `target_type`
 * (`report.target_type === ReportTargetType.FORUM_POST`) lets TypeScript
 * prove which fields exist in that branch, rather than trusting a comment.
 */
export type ReportWithContent = ForumPostReport | DirectMessageReport;

/**
 * A moderator's decision on a report. `decision` is VALID or INVALID —
 * PENDING is the state a report starts in, and the backend rejects it here.
 *
 * The note is required, unlike the nullable moderator_note on Report: rows
 * decided before this endpoint existed carry none, but no new decision may
 * be made without one (SPEC §7.3, "הערת מבקר (לתיעוד)").
 */
export interface ReportDecideRequest {
  decision: ReportDecision;
  note: string;
}

export interface ReportList {
  items: ReportWithContent[];
  total: number;
  pending_count: number;
}

/** Reports already decided in this moderator's cells, newest first. */
export type ReportHistoryList = PaginatedResponse<ReportWithContent>;

// ---------------------------------------------------------------------------
// Automatic restrictions (ABF-116)
// ---------------------------------------------------------------------------

/**
 * The restriction on the *current* user, as she is allowed to see it.
 *
 * Deliberately just the two fields the server sends: what she cannot do and
 * until when. The count of reports behind it stays on the moderator's side —
 * handed back to the person they were filed against it would be a hint about
 * who has been reporting her.
 */
export interface MyRestriction {
  restriction_type: RestrictionType;
  /** Naive-UTC ISO timestamp, like every other date this API returns. */
  expires_at: string;
}

/** GET /messages/restriction — null when there is none, never a 404. */
export interface MyRestrictionResponse {
  restriction: MyRestriction | null;
}

/** The member a restriction applies to, as a moderator dashboard shows her. */
export interface RestrictedMember {
  id: string;
  first_name: string;
  last_name: string;
}

/** One active restriction in a moderator's cells, with the evidence behind it. */
export interface RestrictionWithMember {
  id: string;
  restriction_type: RestrictionType;
  expires_at: string;
  /** How many decided reports were inside the window when it was applied. */
  report_count: number;
  /** The window that count was taken over, in days. */
  window_days: number;
  created_at: string;
  member: RestrictedMember;
}

/** GET /moderator/restrictions — unpaginated, like the pending queue. */
export interface RestrictionList {
  items: RestrictionWithMember[];
  total: number;
}

// ---------------------------------------------------------------------------
// AI agents (backend/app/schemas/agent.py)
// ---------------------------------------------------------------------------

/**
 * One agent in the catalog — GET /agents.
 *
 * `id` is an agent_domains row id (uuid), not an enum: since ABF-120 an agent
 * is a table row an admin can add, gated by group/sector like a forum post.
 * The list a member gets back is already filtered to what they may see, so
 * there is nothing here to filter again on the client.
 *
 * `name` and `description` are written by the association, in Hebrew, and are
 * shown as they came — content, not UI, so they carry no translation key
 * (CONTRIBUTING §6, the rule a professional's own description follows).
 *
 * `professional_domain` is the discipline behind the agent, and the one field
 * the chat screen needs in order to hand the member on to a human: it is what
 * `/advice/ask` pre-selects.
 */
export interface AgentDomain {
  id: string;
  name: string;
  description: string;
  professional_domain: ProfessionalDomain;
}

/**
 * One turn of a conversation, from either side.
 *
 * `content` arrives decrypted — agent_messages.content is AES-256-GCM at rest
 * and the service decrypts on the way out, so nothing on this side knows about
 * ciphertext.
 *
 * An agent turn ends in the association's standing disclaimer, which the
 * backend concatenates onto every answer rather than asking the model for it
 * (agent_service, "the disclaimer is always there"). It is part of the stored
 * row and is rendered with the rest of it.
 */
export interface AgentMessage {
  id: string;
  role: AgentMessageRole;
  /** Naive-UTC ISO timestamp, like every other date this API returns. */
  created_at: string;
  content: string;
}

/**
 * A knowledge base document an answer was drawn from.
 *
 * One per source, not per retrieved passage — the server collapses them. Both
 * provenance fields are optional, because some material is written in-house by
 * the association and has neither a publisher nor a link.
 */
export interface AgentSource {
  title: string;
  source_name: string | null;
  source_url: string | null;
}

/** POST /agents/{domain_id}/chat — omit `conversation_id` to start a thread. */
export interface AgentChatRequest {
  message: string;
  conversation_id?: string;
}

/**
 * One exchange: both rows the server wrote, and what the answer rests on.
 *
 * The question comes back rather than being kept by the client, because its
 * `id` and `created_at` are the server's.
 */
export interface AgentChatResponse {
  conversation_id: string;
  question: AgentMessage;
  answer: AgentMessage;
  sources: AgentSource[];
}

/**
 * GET /agents/{domain_id}/conversations/{id} — a whole thread, in order.
 *
 * No `sources`: provenance belongs to the exchange that produced it and is not
 * stored per message, so a thread re-opened later shows the answers without
 * the document names that were listed under them at the time.
 */
export interface AgentConversation {
  id: string;
  domain_id: string;
  /** Naive-UTC ISO timestamps, like every other date this API returns. */
  started_at: string;
  last_message_at: string;
  messages: AgentMessage[];
}

// ---------------------------------------------------------------------------
// Audit log (ABF-152)
// ---------------------------------------------------------------------------

/**
 * One row of the audit log, as GET /admin/audit-log returns it.
 *
 * The six fields of the frozen contract, and no seventh. In particular **no
 * `ip_address`**: the column exists on the server and is populated, and the
 * decision on ABF-152 is that it reaches no screen under any parameter. It is
 * absent here so that a component cannot reference a field the API will never
 * send, and a reviewer reading this interface sees the same contract the
 * backend's `schemas/audit.py` declares.
 *
 * No actor *name* either, for a reason worth keeping in view: `actor_id` has
 * no foreign key on the server, so that logs outlive the accounts they
 * describe. A name resolved at read time would come back blank for exactly
 * the rows that matter most — the ones about an admin who is gone.
 */
export interface AuditLogEntry {
  id: string;
  actor_id: string;
  /** `action_type` on the wire; the server's column is called `action`. */
  action_type: AuditAction;
  /** Free-form on the server — "User", "ForumPost", "AgentConversation". */
  entity_type: string;
  entity_id: string;
  /** Naive UTC, like every other timestamp this API returns — see utcIso(). */
  timestamp: string;
  /**
   * Context the logging service attached, never PII (CONTRIBUTING §4). Read
   * by the single-entry view (Task 2); the list does not render it.
   */
  details: Record<string, unknown> | null;
}

/**
 * One page of the audit log.
 *
 * Not `PaginatedResponse<AuditLogEntry>`: the frozen contract names the count
 * `total_count`, where every other list in this API calls it `total`. Aliasing
 * the generic would have meant renaming the field on the wire, and the
 * contract is the thing that cannot move.
 */
export interface AuditLogList {
  items: AuditLogEntry[];
  total_count: number;
  page: number;
  page_size: number;
}

/**
 * What the audit log screen is asking for. Every field optional: an absent one
 * is a filter not applied, which is how the service decides what to put in the
 * query string — `actor_id=` with nothing after it is a filter on the empty
 * string, not the absence of a filter.
 */
export interface AuditLogQuery {
  actor_id?: string;
  action_type?: AuditAction;
  entity_type?: string;
  entity_id?: string;
  /** `YYYY-MM-DD`. Inclusive, as is `date_to` — both name whole days. */
  date_from?: string;
  date_to?: string;
  sort?: AuditSortField;
  direction?: SortDirection;
  page?: number;
  page_size?: number;
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
