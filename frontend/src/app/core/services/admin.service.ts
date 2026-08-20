import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
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
}
