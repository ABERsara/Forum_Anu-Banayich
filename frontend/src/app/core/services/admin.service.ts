import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  BroadcastCreate,
  ForumPost,
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
}
