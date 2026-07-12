/**
 * Report service.
 *
 * TODO list for junior developer:
 *   [ ] implement fileReport() – used from any content component
 *   [ ] implement getPendingReports() – moderator use
 *   [ ] implement decideReport() – moderator use
 *   [ ] implement getAuditLog() – admin use
 */

import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Report, ReportCreate, ReportDecideRequest, ReportList } from '../models';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class ReportService {
  private readonly api = inject(ApiService);

  fileReport(data: ReportCreate): Observable<Report> {
    void data;
    /**
     * TODO:
     *   return this.api.post<Report>('/reports', data);
     */
    throw new Error('fileReport() not yet implemented');
  }

  getPendingReports(): Observable<ReportList> {
    /**
     * TODO: (moderator role)
     *   return this.api.get<ReportList>('/moderator/reports');
     */
    throw new Error('getPendingReports() not yet implemented');
  }

  decideReport(reportId: string, data: ReportDecideRequest): Observable<Report> {
    void reportId;
    void data;
    /**
     * TODO: (moderator role)
     *   return this.api.post<Report>(`/moderator/reports/${reportId}/decide`, data);
     */
    throw new Error('decideReport() not yet implemented');
  }

  // Admin
  getAuditLog(page = 1): Observable<unknown[]> {
    void page;
    /**
     * TODO: (admin role)
     *   return this.api.get<unknown[]>(`/admin/audit-log?page=${page}`);
     */
    throw new Error('getAuditLog() not yet implemented');
  }
}
