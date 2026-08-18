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
  SuspendUserRequest,
  UserModerationCard,
} from '../models';
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
    return this.api.get<ReportList>('/moderator/reports');
  }

  /** Reports this moderator's cells already decided, newest first. Paginated. */
  getReportHistory(page = 1): Observable<ReportHistoryList> {
    return this.api.get<ReportHistoryList>(`/moderator/reports/history?page=${page}`);
  }

  decideReport(reportId: string, data: ReportDecideRequest): Observable<Report> {
    return this.api.post<Report>(`/moderator/reports/${reportId}/decide`, data);
  }

  /** One user's moderation history, scoped to the moderator's own cells. */
  getUserCard(userId: string): Observable<UserModerationCard> {
    return this.api.get<UserModerationCard>(`/moderator/users/${userId}/card`);
  }

  /**
   * Suspend a user by hand from their card. Answers with the card as it now
   * stands, so the page does not have to fetch it again.
   */
  suspendUser(userId: string, hours: number, reason: string): Observable<UserModerationCard> {
    const body: SuspendUserRequest = { hours, reason };
    return this.api.post<UserModerationCard>(`/moderator/users/${userId}/suspend`, body);
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
