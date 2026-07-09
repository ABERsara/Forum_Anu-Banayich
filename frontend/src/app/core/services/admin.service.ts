import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { UserAdminView } from '../models';
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
}
