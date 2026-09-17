/**
 * Report service.
 *
 * Moderation, plus the admin's audit log. The audit log is not a report and
 * would sit as well on AdminService — it lives here because the scaffold put
 * `getAuditLog()` here, the audit-log screen has always called it from here,
 * and moving it is a rename across two modules that belongs to a ticket about
 * naming rather than to the one that finally implemented it (ABF-152).
 */

import { Injectable, inject } from '@angular/core';
import { Observable, throwError } from 'rxjs';

import { ReportTargetType } from '../constants';
import {
  AuditLogList,
  AuditLogQuery,
  Report,
  ReportCreate,
  ReportDecideRequest,
  ReportHistoryList,
  ReportList,
  ReportWithContent,
  RestrictionList,
  SuspendUserRequest,
  UserModerationCard,
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

  /**
   * A single report with full content — for a DIRECT_MESSAGE report, this is
   * the one call that ever returns its decrypted text, and the server audits
   * it as a view (ABF-113, spec §9.1/§9.3). Never call this to build a list;
   * getPendingReports()/getReportHistory() already carry everything a list
   * needs without decrypting anything.
   */
  getReport(reportId: string): Observable<ReportWithContent> {
    return this.api.get<ReportWithContent>(`/moderator/reports/${reportId}`);
  }

  /**
   * The automatic restrictions in force right now in this moderator's cells
   * (ABF-116). Unpaginated: it is a picture of the situation now, and it
   * shrinks by itself as restrictions expire.
   */
  getActiveRestrictions(): Observable<RestrictionList> {
    return this.api.get<RestrictionList>('/moderator/restrictions');
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

  /**
   * One filtered, sorted page of the audit log (ABF-152). Admin only — every
   * other role is answered 403 by the API whatever it asks for.
   *
   * The query string is built from the fields that are actually set, and an
   * empty text input counts as unset: `?actor_id=` is a filter on the empty
   * string, which matches nothing, and an admin who cleared a box means "stop
   * filtering by this", not "show me rows with a blank actor".
   *
   * `URLSearchParams` rather than a template literal, following
   * `ForumService.getConversation()`: half of these values come from
   * free-text boxes, and an entity id with an `&` in it pasted straight into
   * a URL stops being one parameter and becomes two.
   */
  getAuditLog(query: AuditLogQuery = {}): Observable<AuditLogList> {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') {
        continue;
      }
      params.set(key, String(value));
    }

    const queryString = params.toString();
    return this.api.get<AuditLogList>(`/admin/audit-log${queryString ? `?${queryString}` : ''}`);
  }
}
