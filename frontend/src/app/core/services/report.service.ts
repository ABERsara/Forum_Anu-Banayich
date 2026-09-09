/**
 * Report service.
 *
 * TODO list for junior developer:
 *   [ ] implement getAuditLog() – admin use
 */

import { Injectable, inject } from '@angular/core';
import { Observable, throwError } from 'rxjs';

import { ReportTargetType } from '../constants';
import {
  Report,
  ReportCreate,
  ReportDecideRequest,
  ReportHistoryList,
  ReportList,
} from '../models';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class ReportService {
  private readonly api = inject(ApiService);

  /**
   * File a report on one piece of content.
   *
   * The route is derived from the target type rather than passed in: each
   * content type is reported to the endpoint that owns it, and a caller that
   * had to name the URL could aim a private-message report at the forum route
   * — which the server rejects, but only after the mistake has been made.
   */
  fileReport(data: ReportCreate): Observable<Report> {
    if (data.target_type === ReportTargetType.FORUM_POST) {
      return this.api.post<Report>(`/forum/posts/${data.target_id}/report`, data);
    }
    if (data.target_type === ReportTargetType.DIRECT_MESSAGE) {
      return this.api.post<Report>(`/messages/${data.target_id}/report`, data);
    }
    return throwError(
      () => new Error(`Reporting ${data.target_type} content is not supported yet.`),
    );
  }

  getPendingReports(): Observable<ReportList> {
    return this.api.get<ReportList>('/moderator/reports');
  }

  /** Reports this moderator's cells already decided, newest first. Paginated. */
  getReportHistory(page = 1): Observable<ReportHistoryList> {
    return this.api.get<ReportHistoryList>(`/moderator/reports/history?page=${page}`);
  }

  decideReport(reportId: string, data: ReportDecideRequest): Observable<Report> {
    return this.api.post<Report>(`/moderator/reports/${reportId}/decide`, data);
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
