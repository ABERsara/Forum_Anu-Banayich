import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { BroadcastCreate, ForumPost, UserAdminView } from '../models';
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
    return this.api.post<UserAdminView>(`/admin/registrations/${userId}/reject`, { reason });
  }
}
