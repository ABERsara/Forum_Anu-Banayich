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
import { Observable, throwError } from 'rxjs';

import { ReportTargetType } from '../constants';
import { Report, ReportCreate, ReportDecideRequest, ReportList } from '../models';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class ReportService {
  private readonly api = inject(ApiService);

  fileReport(data: ReportCreate): Observable<Report> {
    if (data.target_type === ReportTargetType.FORUM_POST) {
      return this.api.post<Report>(`/forum/posts/${data.target_id}/report`, data);
    }
    return throwError(
      () => new Error(`Reporting ${data.target_type} content is not supported yet.`),
    );
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
