import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ModeratorReportsComponent } from './reports.component';
import { ReportService } from '../../../core/services/report.service';
import {
  PostStatus,
  ReportDecision,
  ReportReason,
  ReportTargetType,
} from '../../../core/constants';
import type { ReportHistoryList, ReportWithContent } from '../../../core/models';

function makeReport(overrides: Partial<ReportWithContent> = {}): ReportWithContent {
  return {
    id: 'report-1',
    reporter_id: 'user-1',
    reported_user_id: 'user-2',
    target_type: ReportTargetType.FORUM_POST,
    target_id: 'post-1',
    reason: ReportReason.HARASSMENT,
    description: 'התבטאות פוגענית',
    decision: ReportDecision.PENDING,
    moderator_id: null,
    moderator_note: null,
    decided_at: null,
    created_at: '2026-07-15T09:30:00',
    content_title: 'כותרת ההודעה',
    content_text: 'תוכן ההודעה שדווחה',
    content_status: PostStatus.VISIBLE,
    report_count: 2,
    ...overrides,
  };
}

function makeHistoryPage(overrides: Partial<ReportHistoryList> = {}): ReportHistoryList {
  return {
    items: [
      makeReport({
        id: 'report-9',
        decision: ReportDecision.VALID,
        moderator_note: 'תוכן פוגעני',
        decided_at: '2026-07-16T10:00:00',
        content_status: PostStatus.DELETED,
      }),
    ],
    total: 1,
    page: 1,
    page_size: 20,
    ...overrides,
  };
}

describe('ModeratorReportsComponent', () => {
  let fixture: ComponentFixture<ModeratorReportsComponent>;
  let component: ModeratorReportsComponent;
  let reportServiceMock: {
    getPendingReports: ReturnType<typeof vi.fn>;
    getReportHistory: ReturnType<typeof vi.fn>;
    decideReport: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    reportServiceMock = {
      getPendingReports: vi
        .fn()
        .mockReturnValue(of({ items: [makeReport()], total: 1, pending_count: 1 })),
      getReportHistory: vi.fn().mockReturnValue(of(makeHistoryPage())),
      decideReport: vi.fn().mockReturnValue(of(makeReport({ decision: ReportDecision.VALID }))),
    };

    await TestBed.configureTestingModule({
      imports: [ModeratorReportsComponent],
      providers: [{ provide: ReportService, useValue: reportServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(ModeratorReportsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  describe('the pending queue', () => {
    it('loads the pending reports on init', () => {
      expect(reportServiceMock.getPendingReports).toHaveBeenCalled();
      expect(component.pendingReports().length).toBe(1);
      expect(component.isLoading()).toBe(false);
      expect(component.hasError()).toBe(false);
    });

    it('shows what the decision rests on, without naming the reporter', () => {
      const text: string = fixture.nativeElement.textContent;

      expect(text).toContain('כותרת ההודעה');
      expect(text).toContain('תוכן ההודעה שדווחה');
      expect(text).toContain('הטרדה');
      expect(text).toContain('2 דיווחים');
      expect(text).not.toContain('user-1');
    });

    it('sets hasError when the queue fails to load', () => {
      reportServiceMock.getPendingReports.mockReturnValue(throwError(() => ({})));

      component.ngOnInit();

      expect(component.hasError()).toBe(true);
      expect(component.isLoading()).toBe(false);
    });

    it('truncates a long post to a preview', () => {
      const long = 'א'.repeat(250);

      expect(component.previewOf(long)).toHaveLength(201);
      expect(component.previewOf(long).endsWith('…')).toBe(true);
    });

    it('leaves a short post whole', () => {
      expect(component.previewOf('קצר')).toBe('קצר');
    });
  });

  describe('deciding on a report', () => {
    it('does not call the service until the decision is confirmed', () => {
      component.decide(makeReport(), ReportDecision.VALID);
      fixture.detectChanges();

      expect(reportServiceMock.decideReport).not.toHaveBeenCalled();
      expect(fixture.nativeElement.querySelector('app-confirm-dialog')).toBeTruthy();
    });

    it('sends the decision with the note the moderator wrote', () => {
      component.decide(makeReport(), ReportDecision.VALID);

      component.confirmDecision('תוכן פוגעני');

      expect(reportServiceMock.decideReport).toHaveBeenCalledWith('report-1', {
        decision: ReportDecision.VALID,
        note: 'תוכן פוגעני',
      });
    });

    it('removes the decided report from the pending list', () => {
      component.decide(makeReport(), ReportDecision.INVALID);

      component.confirmDecision('הדיווח אינו מוצדק');

      expect(component.pendingReports()).toEqual([]);
      expect(component.pendingDecision()).toBeNull();
    });

    it('closes the dialog without deciding on cancel', () => {
      component.decide(makeReport(), ReportDecision.VALID);

      component.cancelDecision();

      expect(component.pendingDecision()).toBeNull();
      expect(reportServiceMock.decideReport).not.toHaveBeenCalled();
    });

    it('does nothing when confirmed with no decision open', () => {
      component.confirmDecision('הערה');

      expect(reportServiceMock.decideReport).not.toHaveBeenCalled();
    });

    it('keeps the report in the list and shows the backend message on failure', () => {
      reportServiceMock.decideReport.mockReturnValue(
        throwError(() => ({ error: { detail: 'הדיווח כבר טופל.' } })),
      );
      component.decide(makeReport(), ReportDecision.VALID);

      component.confirmDecision('תוכן פוגעני');

      expect(component.actionError()).toBe('הדיווח כבר טופל.');
      expect(component.pendingReports().length).toBe(1);
    });

    it('falls back to a generic message when the failure carries no detail', () => {
      reportServiceMock.decideReport.mockReturnValue(throwError(() => ({ error: null })));
      component.decide(makeReport(), ReportDecision.VALID);

      component.confirmDecision('תוכן פוגעני');

      expect(component.actionError()).toBe('אירעה שגיאה בשמירת ההחלטה. נסי שוב.');
    });

    it('warns that deletion is destructive, and that dismissal is not', () => {
      expect(component.confirmTitle(ReportDecision.VALID)).toBe('מחיקת ההודעה');
      expect(component.confirmMessage(ReportDecision.VALID)).toContain('תוסר מהפורום');
      expect(component.confirmTitle(ReportDecision.INVALID)).toBe('ביטול הדיווח');
      expect(component.confirmMessage(ReportDecision.INVALID)).toContain('תוצג שוב');
    });
  });

  describe('the history tab', () => {
    it('does not fetch history before the tab is opened', () => {
      expect(reportServiceMock.getReportHistory).not.toHaveBeenCalled();
    });

    it('reaches the unselected tab with the arrow keys, and focuses it', () => {
      const historyTab: HTMLElement = fixture.nativeElement.querySelector('#tab-history');

      component.moveToTab(
        new KeyboardEvent('keydown', { key: 'ArrowLeft' }),
        'history',
        historyTab,
      );

      expect(component.activeTab()).toBe('history');
      expect(document.activeElement).toBe(historyTab);
    });

    it('leaves other keys to the browser', () => {
      const historyTab: HTMLElement = fixture.nativeElement.querySelector('#tab-history');

      component.moveToTab(new KeyboardEvent('keydown', { key: 'Tab' }), 'history', historyTab);

      expect(component.activeTab()).toBe('pending');
    });

    it('loads history the first time the tab is opened', () => {
      component.showTab('history');

      expect(reportServiceMock.getReportHistory).toHaveBeenCalledWith(1);
      expect(component.history().length).toBe(1);
      expect(component.isHistoryLoading()).toBe(false);
    });

    it('shows the past decision and the note behind it', () => {
      component.showTab('history');
      fixture.detectChanges();

      const text: string = fixture.nativeElement.textContent;
      expect(text).toContain('הדיווח התקבל');
      expect(text).toContain('תוכן פוגעני');
      expect(text).toContain('מחוק');
      expect(text).toContain('16/07/2026');
    });

    it('does not refetch when switching back to a history it already holds', () => {
      component.showTab('history');
      component.showTab('pending');
      component.showTab('history');

      expect(reportServiceMock.getReportHistory).toHaveBeenCalledTimes(1);
    });

    it('refetches history after a decision, which has just changed it', () => {
      component.showTab('history');
      component.showTab('pending');
      component.decide(makeReport(), ReportDecision.VALID);
      component.confirmDecision('תוכן פוגעני');

      component.showTab('history');

      expect(reportServiceMock.getReportHistory).toHaveBeenCalledTimes(2);
    });

    it('sets historyError when history fails to load', () => {
      reportServiceMock.getReportHistory.mockReturnValue(throwError(() => ({})));

      component.showTab('history');

      expect(component.historyError()).toBe(true);
      expect(component.isHistoryLoading()).toBe(false);
    });

    it('reports a single page when everything fits on one', () => {
      component.showTab('history');

      expect(component.historyPageCount()).toBe(1);
      expect(component.hasPreviousPage()).toBe(false);
      expect(component.hasNextPage()).toBe(false);
    });

    it('derives the page count from the total and the page size', () => {
      reportServiceMock.getReportHistory.mockReturnValue(
        of(makeHistoryPage({ total: 5, page: 1, page_size: 2 })),
      );

      component.showTab('history');

      expect(component.historyPageCount()).toBe(3);
      expect(component.hasNextPage()).toBe(true);
    });

    it('pages forward and back', () => {
      reportServiceMock.getReportHistory.mockReturnValue(
        of(makeHistoryPage({ total: 5, page: 2, page_size: 2 })),
      );
      component.showTab('history');

      component.goToNextPage();
      expect(reportServiceMock.getReportHistory).toHaveBeenLastCalledWith(3);

      component.goToPreviousPage();
      expect(reportServiceMock.getReportHistory).toHaveBeenLastCalledWith(1);
    });

    it('does not page past the ends', () => {
      component.showTab('history');
      reportServiceMock.getReportHistory.mockClear();

      component.goToPreviousPage();
      component.goToNextPage();

      expect(reportServiceMock.getReportHistory).not.toHaveBeenCalled();
    });

    it('reports an empty history rather than showing nothing', () => {
      reportServiceMock.getReportHistory.mockReturnValue(
        of(makeHistoryPage({ items: [], total: 0 })),
      );

      component.showTab('history');
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('עדיין לא התקבלו החלטות');
    });
  });
});
