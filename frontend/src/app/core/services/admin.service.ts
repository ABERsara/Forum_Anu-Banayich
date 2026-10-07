import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AuditLogEntry,
  AuditLogList,
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
   * One filtered, sorted page of the audit log (ABF-152). Admin only — every
   * other role is answered 403 by the API whatever it asks for.
   *
   * The query string is built from the fields that are actually set, and an
   * empty text input counts as unset: `?actor_id=` is a filter on the empty
   * string, which matches nothing, and an admin who cleared a box means "stop
   * filtering by this", not "show me rows with a blank actor".
   *
   * `URLSearchParams` rather than a template literal, following
   * `ForumService.getConversation()`: half of these values come from
   * free-text boxes, and an entity id with an `&` in it pasted straight into
   * a URL stops being one parameter and becomes two.
   */
  getAuditLog(query: AuditLogQuery = {}): Observable<AuditLogList> {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') {
        continue;
      }
      params.set(key, String(value));
    }

    const queryString = params.toString();
    return this.api.get<AuditLogList>(`/admin/audit-log${queryString ? `?${queryString}` : ''}`);
  }

  /**
   * One audit log entry in full — what a row of the list opens onto
   * (ABF-153). Admin only, like the list: any other role gets 403, for an id
   * that exists and for one that does not.
   *
   * The id is encoded even though the server only ever mints UUIDs: it is a
   * path segment, and a value with a `/` or `?` in it would otherwise address
   * a different route rather than a missing entry.
   */
  getAuditLogEntry(entryId: string): Observable<AuditLogEntry> {
    return this.api.get<AuditLogEntry>(`/admin/audit-log/${encodeURIComponent(entryId)}`);
  }
}
