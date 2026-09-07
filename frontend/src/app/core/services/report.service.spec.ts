import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ReportService } from './report.service';
import { environment } from '../../../environments/environment';
import { ReportDecision, ReportReason, ReportTargetType } from '../constants';
import type { Report, ReportCreate } from '../models';

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
});
