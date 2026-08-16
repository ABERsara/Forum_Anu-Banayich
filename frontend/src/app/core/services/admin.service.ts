import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  BroadcastCreate,
  ForumPost,
  ModeratorAdminView,
  ModeratorCreateRequest,
  ModeratorUpdateRequest,
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

  getRegistration(userId: string): Observable<UserAdminView> {
    return this.api.get<UserAdminView>(`/admin/registrations/${userId}`);
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
}
