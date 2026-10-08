import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AuditLogList,
  AuditLogFilters,
  AuditLogQuery,
  BroadcastCreate,
  ForumPost,
  ModeratorAdminView,
  ModeratorCreateRequest,
  ModeratorUpdateRequest,
  ProfessionalAdminView,
  ProfessionalCreateRequest,
  ProfessionalUpdateRequest,
  RegistrationDetail,
  RegistrationRejectRequest,
  SuspendUserRequest,
  UserAdminView,
} from '../models';
import { ApiService } from './api.service';

/**
 * The audit log's query string — `?a=1&b=2`, or nothing at all when nothing is
 * set. Shared by the screen's page request and the CSV export (ABF-161), so the
 * file is cut by exactly the parameters the screen was fetched with.
 *
 * Built from the fields that are actually set, and an empty text input counts
 * as unset: `?actor_id=` is a filter on the empty string, which matches
 * nothing, and an admin who cleared a box means "stop filtering by this", not
 * "show me rows with a blank actor". No `?` when there is nothing after it,
 * either: that is a different URL from the one the caller described.
 *
 * `URLSearchParams` rather than a template literal, following
 * `ForumService.getConversation()`: half of these values come from free-text
 * boxes, and an entity id with an `&` in it pasted straight into a URL stops
 * being one parameter and becomes two.
 */
function auditLogSearch(query: AuditLogQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') {
      continue;
    }
    params.set(key, String(value));
  }

  const queryString = params.toString();
  return queryString ? `?${queryString}` : '';
}

@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly api = inject(ApiService);

  getPendingRegistrations(): Observable<UserAdminView[]> {
    return this.api.get<UserAdminView[]>('/admin/registrations');
  }

  sendBroadcast(data: BroadcastCreate): Observable<ForumPost> {
    return this.api.post<ForumPost>('/forum/broadcast', data);
  }

  /**
   * One registration from the queue, with the documents filed with it.
   *
   * Answers 403 once the registration is no longer waiting for a decision —
   * another admin got there first, and the queue in this browser is stale.
   */
  getRegistration(userId: string): Observable<RegistrationDetail> {
    return this.api.get<RegistrationDetail>(`/admin/registrations/${userId}`);
  }

  approveRegistration(userId: string): Observable<UserAdminView> {
    return this.api.post<UserAdminView>(`/admin/registrations/${userId}/approve`, {});
  }

  rejectRegistration(userId: string, reason: string): Observable<UserAdminView> {
    const body: RegistrationRejectRequest = { reason };
    return this.api.post<UserAdminView>(`/admin/registrations/${userId}/reject`, body);
  }

  getActiveUsers(): Observable<UserAdminView[]> {
    return this.api.get<UserAdminView[]>('/admin/users/active');
  }

  suspendUser(userId: string, hours: number, reason: string): Observable<UserAdminView> {
    const body: SuspendUserRequest = { hours, reason };
    return this.api.post<UserAdminView>(`/admin/users/${userId}/suspend`, body);
  }

  /** Users with an active report restriction (§7.2's hardened measure, ABF-154). */
  getRestrictedUsers(): Observable<UserAdminView[]> {
    return this.api.get<UserAdminView[]>('/admin/users/restricted');
  }

  liftRestriction(userId: string): Observable<UserAdminView> {
    return this.api.patch<UserAdminView>(`/admin/users/${userId}/lift-restriction`, {});
  }

  /** The moderator roster: every appointed moderator with their cells. */
  getModerators(): Observable<ModeratorAdminView[]> {
    return this.api.get<ModeratorAdminView[]>('/admin/moderators');
  }

  addModerator(data: ModeratorCreateRequest): Observable<ModeratorAdminView> {
    return this.api.post<ModeratorAdminView>('/admin/moderators', data);
  }

  updateModerator(userId: string, data: ModeratorUpdateRequest): Observable<ModeratorAdminView> {
    return this.api.patch<ModeratorAdminView>(`/admin/moderators/${userId}`, data);
  }

  /** Takes the moderator off the roster. The endpoint answers 204, no body. */
  removeModerator(userId: string): Observable<void> {
    return this.api.delete<void>(`/admin/moderators/${userId}`);
  }

  /** The whole catalog, including professionals currently unlisted. */
  getProfessionals(): Observable<ProfessionalAdminView[]> {
    return this.api.get<ProfessionalAdminView[]>('/admin/professionals');
  }

  addProfessional(data: ProfessionalCreateRequest): Observable<ProfessionalAdminView> {
    return this.api.post<ProfessionalAdminView>('/admin/professionals', data);
  }

  updateProfessional(
    userId: string,
    data: ProfessionalUpdateRequest,
  ): Observable<ProfessionalAdminView> {
    return this.api.put<ProfessionalAdminView>(`/admin/professionals/${userId}`, data);
  }

  /**
   * The audit log as a CSV file, cut by the filters the screen has applied
   * (ABF-161). Admin only, like the list.
   *
   * Filters only — `AuditLogFilters` has no sort, direction or page, because
   * the file is every matching row, not the page on screen.
   *
   * The body comes back as the server's own bytes (`ApiService.getBlob`), BOM
   * included, which is what lets Excel read the Hebrew in it.
   */
  exportAuditLog(filters: AuditLogFilters = {}): Observable<Blob> {
    return this.api.getBlob(`/admin/audit-log/export${auditLogSearch(filters)}`);
  }

  /**
   * One filtered, sorted page of the audit log (ABF-152). Admin only — every
   * other role is answered 403 by the API whatever it asks for. The query
   * string is `auditLogSearch()`'s, above.
   */
  getAuditLog(query: AuditLogQuery = {}): Observable<AuditLogList> {
    return this.api.get<AuditLogList>(`/admin/audit-log${auditLogSearch(query)}`);
  }
}
