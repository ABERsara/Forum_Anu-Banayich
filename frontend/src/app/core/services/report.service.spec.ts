import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ReportService } from './report.service';
import { environment } from '../../../environments/environment';
import {
  PostStatus,
  ReportDecision,
  ReportReason,
  ReportTargetType,
  RestrictionType,
} from '../constants';
import type {
  Report,
  ReportCreate,
  ReportHistoryList,
  ReportWithContent,
  RestrictionList,
} from '../models';

const MOCK_REPORT: Report = {
  id: 'report-1',
  reporter_id: 'user-1',
  reported_user_id: 'user-2',
  target_type: ReportTargetType.FORUM_POST,
  target_id: 'post-1',
  reason: ReportReason.HARASSMENT,
  description: null,
  decision: ReportDecision.PENDING,
  moderator_id: null,
  moderator_note: null,
  decided_at: null,
  created_at: '2026-07-15T00:00:00',
};

describe('ReportService', () => {
  let service: ReportService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ReportService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('fileReport POSTs to the forum post report endpoint and returns the created report', () => {
    const data: ReportCreate = {
      target_type: ReportTargetType.FORUM_POST,
      target_id: 'post-1',
      reason: ReportReason.HARASSMENT,
    };
    let result: Report | undefined;
    service.fileReport(data).subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/forum/posts/post-1/report`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(data);

    req.flush(MOCK_REPORT);
    expect(result).toEqual(MOCK_REPORT);
  });

  it('fileReport POSTs a private-message report to the messages endpoint', () => {
    const data: ReportCreate = {
      target_type: ReportTargetType.DIRECT_MESSAGE,
      target_id: 'msg-1',
      reason: ReportReason.SPAM,
    };
    let result: Report | undefined;
    service.fileReport(data).subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/messages/msg-1/report`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(data);

    req.flush({ ...MOCK_REPORT, target_type: ReportTargetType.DIRECT_MESSAGE });
    expect(result?.target_type).toBe(ReportTargetType.DIRECT_MESSAGE);
  });

  /**
   * A private message is never reported through the forum route: that route
   * would look a post up by a message id, and the answer would say something
   * about forum posts in reply to a question about a private message.
   */
  it('never aims a private-message report at the forum route', () => {
    service
      .fileReport({
        target_type: ReportTargetType.DIRECT_MESSAGE,
        target_id: 'msg-1',
        reason: ReportReason.SPAM,
      })
      .subscribe();

    httpMock.expectNone(`${environment.apiUrl}/forum/posts/msg-1/report`);
    httpMock.expectOne(`${environment.apiUrl}/messages/msg-1/report`).flush(MOCK_REPORT);
  });

  it('fileReport returns an error observable for target types without a wired endpoint yet', () => {
    const data: ReportCreate = {
      target_type: ReportTargetType.PROFESSIONAL_QUERY,
      target_id: 'query-1',
      reason: ReportReason.SPAM,
    };

    let error: unknown;
    service.fileReport(data).subscribe({ error: (err) => (error = err) });

    expect(error).toBeInstanceOf(Error);
  });

  it('getPendingReports GETs the moderator queue', () => {
    service.getPendingReports().subscribe();

    const req = httpMock.expectOne(`${environment.apiUrl}/moderator/reports`);
    expect(req.request.method).toBe('GET');
    req.flush({ items: [], total: 0, pending_count: 0 });
  });

  it('decideReport POSTs the decision and the note to the decide endpoint', () => {
    const decided: Report = {
      ...MOCK_REPORT,
      decision: ReportDecision.VALID,
      moderator_id: 'mod-1',
      moderator_note: 'תוכן פוגעני',
      decided_at: '2026-07-16T10:00:00',
    };
    let result: Report | undefined;

    service
      .decideReport('report-1', { decision: ReportDecision.VALID, note: 'תוכן פוגעני' })
      .subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/moderator/reports/report-1/decide`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ decision: ReportDecision.VALID, note: 'תוכן פוגעני' });

    req.flush(decided);
    expect(result).toEqual(decided);
  });

  it('getReportHistory GETs the first page by default', () => {
    const page: ReportHistoryList = { items: [], total: 0, page: 1, page_size: 20 };
    let result: ReportHistoryList | undefined;

    service.getReportHistory().subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/moderator/reports/history?page=1`);
    expect(req.request.method).toBe('GET');

    req.flush(page);
    expect(result).toEqual(page);
  });

  it('getReportHistory asks for the requested page', () => {
    const decided: ReportWithContent = {
      ...MOCK_REPORT,
      decision: ReportDecision.INVALID,
      content_title: 'כותרת',
      content_text: 'תוכן',
      content_status: PostStatus.VISIBLE,
      report_count: 1,
    };
    let result: ReportHistoryList | undefined;

    service.getReportHistory(3).subscribe((res) => (result = res));

    const req = httpMock.expectOne(`${environment.apiUrl}/moderator/reports/history?page=3`);
    req.flush({ items: [decided], total: 5, page: 3, page_size: 2 });

    expect(result?.items).toEqual([decided]);
  });

  it('getActiveRestrictions GETs the moderator restrictions list', () => {
    const restrictions: RestrictionList = {
      items: [
        {
          id: 'restriction-1',
          restriction_type: RestrictionType.MESSAGING,
          expires_at: '2026-07-18T09:30:00',
          report_count: 3,
          window_days: 30,
          created_at: '2026-07-16T09:30:00',
          member: { id: 'user-2', first_name: 'דנה', last_name: 'לוי' },
        },
      ],
      total: 1,
    };
    let result: RestrictionList | undefined;

    service.getActiveRestrictions().subscribe((res) => (result = res));

    // No page parameter: the list is what is in force now, and it shrinks by
    // itself as restrictions expire.
    const req = httpMock.expectOne(`${environment.apiUrl}/moderator/restrictions`);
    expect(req.request.method).toBe('GET');

    req.flush(restrictions);
    expect(result).toEqual(restrictions);
  });
});
