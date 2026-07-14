import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { RegistrationRejectRequest, SuspendUserRequest, UserAdminView } from '../models';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly api = inject(ApiService);

  getPendingRegistrations(): Observable<UserAdminView[]> {
    return this.api.get<UserAdminView[]>('/admin/registrations');
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
}
