/**
 * The moderator reports board, on both counts it has to get right.
 *
 * `the pending queue` / `deciding on a report` / `the history tab` pin the
 * behaviour ABF-105 and ABF-100 built: what the moderator is shown before a
 * decision, that no decision is sent without a confirmed note, and that the
 * history reflects the decision just taken.
 *
 * `i18n` is the guard ABF-134 wrote for the scaffold this screen replaced,
 * carried onto the screen that replaced it. Without it nothing catches a label
 * that fell back to hardcoded Hebrew, a raw `moderator.reports.title` reaching
 * the page, or — the one a reading of the diff will not catch — an `aria-label`
 * that stayed Hebrew while the visible text was translated.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ModeratorReportsComponent } from './reports.component';
import { ReportService } from '../../../core/services/report.service';
import {
  PostStatus,
  ReportDecision,
  ReportReason,
  ReportTargetType,
  RestrictionType,
} from '../../../core/constants';
import type {
  DirectMessageReport,
  ForumPostReport,
  ReportHistoryList,
  RestrictionList,
} from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

// Partial<ForumPostReport>, not Partial<ReportWithContent>: the latter is a
// discriminated union, and Partial<A | B> collapses to the fields A and B
// share — it would silently stop allowing overrides of content_text etc.
// This builder only ever returns the FORUM_POST shape anyway.
function makeReport(overrides: Partial<ForumPostReport> = {}): ForumPostReport {
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

/**
 * A report whose reported content carries no Hebrew.
 *
 * The post's title, its body and the words the reporter typed are
 * user-generated content — never translated (ABF-130). Feeding Latin content
 * to the `HEBREW` sweeps below keeps them pointed at our own copy, which is
 * the thing they are meant to guard.
 */
function makeLatinReport(overrides: Partial<ForumPostReport> = {}): ForumPostReport {
  return makeReport({
    content_title: 'A post about the paperwork',
    content_text: 'Body text',
    description: 'The author is swearing',
    ...overrides,
  });
}

function makeDirectMessageReport(
  overrides: Partial<DirectMessageReport> = {},
): DirectMessageReport {
  return {
    id: 'report-dm-1',
    reporter_id: 'user-3',
    reported_user_id: 'user-4',
    target_type: ReportTargetType.DIRECT_MESSAGE,
    target_id: 'message-1',
    reason: ReportReason.HARASSMENT,
    description: null,
    decision: ReportDecision.PENDING,
    moderator_id: null,
    moderator_note: null,
    decided_at: null,
    created_at: '2026-07-15T09:30:00',
    ...overrides,
  };
}

function makeRestrictions(overrides: Partial<RestrictionList> = {}): RestrictionList {
  return {
    items: [
      {
        id: 'restriction-1',
        restriction_type: RestrictionType.MESSAGING,
        expires_at: '2026-07-18T09:30:00',
        report_count: 3,
        window_days: 30,
        created_at: '2026-07-16T09:30:00',
        member: { id: 'user-2', first_name: 'Dana', last_name: 'Levi' },
      },
    ],
    total: 1,
    ...overrides,
  };
}

/**
 * The other direction of ABF-116, as the dashboard receives it: a member whose
 * own reports keep being dismissed. Same shape, same `report_count` field —
 * and the count means the opposite of what it means above.
 */
function makeReportingRestrictions(): RestrictionList {
  return makeRestrictions({
    items: [
      {
        id: 'restriction-2',
        restriction_type: RestrictionType.REPORTING,
        expires_at: '2026-08-15T09:30:00',
        report_count: 5,
        window_days: 30,
        created_at: '2026-07-16T09:30:00',
        member: { id: 'user-3', first_name: 'Rivka', last_name: 'Cohen' },
      },
    ],
  });
}

/**
 * A naive-UTC timestamp as this runner's clock renders it, in the screen's
 * `dd/MM/yyyy HH:mm`.
 *
 * Derived rather than hardcoded: the dates on a restriction row arrive as
 * naive UTC and the column shows them in the moderator's own zone, so the
 * digits differ between CI (UTC) and a machine in Israel (UTC+3). A literal
 * here would pin one of the two and fail on the other — the same reason
 * chat.component.spec.ts derives its `formattedEnd`.
 */
function wallClock(naiveUtc: string): string {
  const at = new Date(`${naiveUtc}Z`);
  const pad = (value: number): string => String(value).padStart(2, '0');
  return (
    `${pad(at.getDate())}/${pad(at.getMonth() + 1)}/${at.getFullYear()} ` +
    `${pad(at.getHours())}:${pad(at.getMinutes())}`
  );
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
    getActiveRestrictions: ReturnType<typeof vi.fn>;
    getReport: ReturnType<typeof vi.fn>;
    decideReport: ReturnType<typeof vi.fn>;
  };

  /**
   * Builds the screen; `pending`, `history`, `restrictions` and `content`
   * (the response GET /reports/{id} — a DIRECT_MESSAGE report's decrypted
   * content — hands back) override the default fixtures.
   */
  async function render({
    pending = of({ items: [makeReport()], total: 1, pending_count: 1 }),
    history = of(makeHistoryPage()),
    restrictions = of(makeRestrictions()),
    content = of(makeDirectMessageReport({ message_content: 'תוכן ההודעה המפוענח' })),
  }: {
    pending?: unknown;
    history?: unknown;
    restrictions?: unknown;
    content?: unknown;
  } = {}): Promise<void> {
    TestBed.resetTestingModule();

    reportServiceMock = {
      getPendingReports: vi.fn().mockReturnValue(pending),
      getReportHistory: vi.fn().mockReturnValue(history),
      getActiveRestrictions: vi.fn().mockReturnValue(restrictions),
      getReport: vi.fn().mockReturnValue(content),
      decideReport: vi.fn().mockReturnValue(of(makeReport({ decision: ReportDecision.VALID }))),
    };

    await TestBed.configureTestingModule({
      imports: [ModeratorReportsComponent, translocoTesting()],
      providers: [{ provide: ReportService, useValue: reportServiceMock }, provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(ModeratorReportsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function root(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return root().textContent ?? '';
  }

  function heading(): string {
    return root().querySelector('h1')!.textContent!.trim();
  }

  function cards(): HTMLElement[] {
    return [...root().querySelectorAll<HTMLElement>('.reports__item')];
  }

  /** One card's `<dt>: <dd>` rows, whitespace collapsed. */
  function fieldsOf(card: HTMLElement): string[] {
    return [...card.querySelectorAll('.reports__meta > div')].map((row) => {
      const term = row.querySelector('dt')!.textContent!.replace(/\s+/g, ' ').trim();
      const value = row.querySelector('dd')!.textContent!.replace(/\s+/g, ' ').trim();
      return `${term}: ${value}`;
    });
  }

  /** The tab buttons in the order the tablist renders them. */
  function tabButtons(): HTMLElement[] {
    return [...root().querySelectorAll<HTMLElement>('.tabs__tab')];
  }

  function tabLabels(): string[] {
    return [...root().querySelectorAll('.tabs__tab')].map((tab) =>
      tab.textContent!.replace(/\s+/g, ' ').trim(),
    );
  }

  function actionLabels(): string[] {
    return [...root().querySelectorAll('.reports__actions > *')].map((action) =>
      action.textContent!.replace(/\s+/g, ' ').trim(),
    );
  }

  /** A button inside `container` whose visible text matches exactly. */
  function findButton(container: HTMLElement, label: string): HTMLButtonElement | null {
    return (
      [...container.querySelectorAll('button')].find(
        (button) => button.textContent!.replace(/\s+/g, ' ').trim() === label,
      ) ?? null
    );
  }

  function ariaLabels(): string[] {
    return [...root().querySelectorAll('[aria-label]')].map(
      (element) => element.getAttribute('aria-label')!,
    );
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await render();
  });

  describe('the pending queue', () => {
    it('loads the pending reports on init', () => {
      expect(reportServiceMock.getPendingReports).toHaveBeenCalled();
      expect(component.pendingReports().length).toBe(1);
      expect(component.isLoading()).toBe(false);
      expect(component.hasError()).toBe(false);
    });

    it('shows what the decision rests on, without naming the reporter', () => {
      expect(text()).toContain('כותרת ההודעה');
      expect(text()).toContain('תוכן ההודעה שדווחה');
      expect(text()).toContain('הטרדה');
      expect(text()).toContain('2 דיווחים');
      expect(text()).not.toContain('user-1');
    });

    /**
     * ABF-155. A row is a preview: the post is cut at 200 characters and the
     * decision record is not on it at all. Without this link the screen that
     * holds the rest was reachable only by typing its URL.
     */
    it('opens the way through to the report in full', () => {
      const link: HTMLAnchorElement = root().querySelector('.reports__detail-link')!;

      expect(link.getAttribute('href')).toBe('/moderator/reports/report-1');
      expect(link.getAttribute('aria-label')).toContain('כותרת ההודעה');
    });

    it('opens the way through to the card of the reported user', () => {
      const link: HTMLAnchorElement = root().querySelector('.reports__card-link')!;

      expect(link.getAttribute('href')).toBe('/moderator/users/user-2');
      expect(link.getAttribute('aria-label')).toContain('כותרת ההודעה');
    });

    it('shows a spinner instead of the list while the request is in flight', async () => {
      await render({ pending: NEVER });

      expect(component.isLoading()).toBe(true);
      expect(root().querySelector('app-loading-spinner')).toBeTruthy();
      expect(cards()).toEqual([]);
    });

    it('sets hasError when the queue fails to load', async () => {
      await render({ pending: throwError(() => ({})) });

      expect(component.hasError()).toBe(true);
      expect(component.isLoading()).toBe(false);
      expect(root().querySelector('app-error-display')).toBeTruthy();
      expect(text()).not.toContain('אין דיווחים ממתינים');
    });

    it('says so when there is nothing waiting', async () => {
      await render({ pending: of({ items: [], total: 0, pending_count: 0 }) });

      expect(cards()).toEqual([]);
      expect(text()).toContain('אין דיווחים ממתינים. כל הכבוד!');
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
      expect(root().querySelector('app-confirm-dialog')).toBeTruthy();
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
      fixture.detectChanges();

      expect(component.actionError()).toEqual({ key: '', text: 'הדיווח כבר טופל.' });
      expect(text()).toContain('הדיווח כבר טופל.');
      expect(component.pendingReports().length).toBe(1);
    });

    it('falls back to a key of ours when the failure carries no detail', () => {
      reportServiceMock.decideReport.mockReturnValue(throwError(() => ({ error: null })));
      component.decide(makeReport(), ReportDecision.VALID);

      component.confirmDecision('תוכן פוגעני');
      fixture.detectChanges();

      expect(component.actionError()).toEqual({
        key: 'moderator.errors.decide_failed',
        text: '',
      });
      expect(text()).toContain('אירעה שגיאה בשמירת ההחלטה. נסי שוב.');
    });

    it('warns that deletion is destructive, and that dismissal is not', () => {
      component.decide(makeReport(), ReportDecision.VALID);
      fixture.detectChanges();
      const dialog = root().querySelector('app-confirm-dialog')!;

      expect(dialog.textContent).toContain('מחיקת ההודעה');
      expect(dialog.textContent).toContain('תוסר מהפורום');

      component.decide(makeReport(), ReportDecision.INVALID);
      fixture.detectChanges();

      expect(root().querySelector('app-confirm-dialog')!.textContent).toContain('תוצג שוב');
    });
  });

  /**
   * ABF-113: a moderator can open one DIRECT_MESSAGE report and read the
   * decrypted content, through the same viewer the pending queue and the
   * history tab both pull in via dmContentViewer. Unlike a FORUM_POST row,
   * a DM report never carries its content in the list itself — only this
   * one audited fetch, triggered by hand, ever decrypts it.
   */
  describe('viewing a DIRECT_MESSAGE report’s content', () => {
    async function renderWithPendingDm(...reports: DirectMessageReport[]): Promise<HTMLElement[]> {
      await render({
        pending: of({ items: reports, total: reports.length, pending_count: reports.length }),
      });
      fixture.detectChanges();
      return cards();
    }

    it('shows no content preview in the list, only a button to fetch it', async () => {
      const [card] = await renderWithPendingDm(makeDirectMessageReport());

      expect(card.textContent).not.toContain('תוכן ההודעה המפוענח');
      expect(reportServiceMock.getReport).not.toHaveBeenCalled();
      expect(findButton(card, 'הצג תוכן ההודעה')).toBeTruthy();
    });

    it('falls back to a generic title — a DM report has none of its own', async () => {
      const [card] = await renderWithPendingDm(makeDirectMessageReport());

      expect(card.querySelector('.reports__title')!.textContent!.trim()).toBe('הודעה פרטית');
    });

    it('fetches and shows the decrypted content on request', async () => {
      const [card] = await renderWithPendingDm(makeDirectMessageReport({ id: 'report-dm-1' }));

      findButton(card, 'הצג תוכן ההודעה')!.click();
      fixture.detectChanges();

      expect(reportServiceMock.getReport).toHaveBeenCalledWith('report-dm-1');
      expect(card.textContent).toContain('תוכן ההודעה המפוענח');
      expect(findButton(card, 'הסתר תוכן')).toBeTruthy();
      expect(findButton(card, 'הצג תוכן ההודעה')).toBeNull();
    });

    it('shows a spinner while the content is in flight', async () => {
      await render({
        pending: of({ items: [makeDirectMessageReport()], total: 1, pending_count: 1 }),
        content: NEVER,
      });
      const [card] = cards();

      findButton(card, 'הצג תוכן ההודעה')!.click();
      fixture.detectChanges();

      expect(component.isContentLoading()).toBe(true);
      expect(card.querySelector('app-loading-spinner')).toBeTruthy();
    });

    it('shows an error, and no content, when the fetch fails', async () => {
      await render({
        pending: of({ items: [makeDirectMessageReport()], total: 1, pending_count: 1 }),
        content: throwError(() => ({ error: null })),
      });
      const [card] = cards();

      findButton(card, 'הצג תוכן ההודעה')!.click();
      fixture.detectChanges();

      expect(card.querySelector('app-error-display')).toBeTruthy();
      expect(component.isContentLoading()).toBe(false);
      expect(card.textContent).not.toContain('תוכן ההודעה המפוענח');
    });

    it('closes the content and returns to the "view" button', async () => {
      const [card] = await renderWithPendingDm(makeDirectMessageReport());
      findButton(card, 'הצג תוכן ההודעה')!.click();
      fixture.detectChanges();

      findButton(card, 'הסתר תוכן')!.click();
      fixture.detectChanges();

      expect(component.openReportId()).toBeNull();
      expect(findButton(card, 'הצג תוכן ההודעה')).toBeTruthy();
      expect(card.textContent).not.toContain('תוכן ההודעה המפוענח');
    });

    /**
     * A second click may move on to another report before the first request
     * resolves. That request's own response belongs to the report it was
     * fetched for — not to whichever report happens to be open once it
     * lands (viewContent()'s isOpen() guard, copied from the same race this
     * screen already had to close on the pending list itself).
     */
    it('ignores a stale response for a report that is no longer open', async () => {
      const firstRequest = new Subject<DirectMessageReport>();
      const [firstCard, secondCard] = await renderWithPendingDm(
        makeDirectMessageReport({ id: 'report-dm-1' }),
        makeDirectMessageReport({ id: 'report-dm-2', target_id: 'message-2' }),
      );
      reportServiceMock.getReport.mockReturnValueOnce(firstRequest);

      findButton(firstCard, 'הצג תוכן ההודעה')!.click();
      fixture.detectChanges();
      findButton(secondCard, 'הצג תוכן ההודעה')!.click();
      fixture.detectChanges();

      firstRequest.next(
        makeDirectMessageReport({ id: 'report-dm-1', message_content: 'לא אמור להיות מוצג' }),
      );
      fixture.detectChanges();

      expect(text()).not.toContain('לא אמור להיות מוצג');
      expect(secondCard.textContent).toContain('תוכן ההודעה המפוענח');
    });

    it('closes any open content once a decision is confirmed', async () => {
      const [card] = await renderWithPendingDm(makeDirectMessageReport());
      findButton(card, 'הצג תוכן ההודעה')!.click();
      fixture.detectChanges();

      component.decide(makeDirectMessageReport(), ReportDecision.INVALID);
      component.confirmDecision('הדיווח אינו מוצדק');

      expect(component.openReportId()).toBeNull();
      expect(component.openReportContent()).toBeNull();
    });

    describe('in the history tab', () => {
      it('shows a fixed note when the account was deleted, and no view button', async () => {
        await render({
          history: of({
            items: [
              makeDirectMessageReport({
                id: 'report-dm-9',
                decision: ReportDecision.CLOSED_ACCOUNT_DELETED,
              }),
            ],
            total: 1,
            page: 1,
            page_size: 20,
          }),
        });
        component.showTab('history');
        fixture.detectChanges();
        const [card] = cards();

        expect(card.textContent).toContain('הדיווח נסגר עקב מחיקת חשבון');
        expect(findButton(card, 'הצג תוכן ההודעה')).toBeNull();
        expect(reportServiceMock.getReport).not.toHaveBeenCalled();
      });

      it('still lets the content be viewed for a decided DM report', async () => {
        await render({
          history: of({
            items: [
              makeDirectMessageReport({
                id: 'report-dm-8',
                decision: ReportDecision.VALID,
                decided_at: '2026-07-16T10:00:00',
                moderator_note: 'תוכן פוגעני',
              }),
            ],
            total: 1,
            page: 1,
            page_size: 20,
          }),
          content: of(
            makeDirectMessageReport({ id: 'report-dm-8', message_content: 'ההודעה שהוסרה' }),
          ),
        });
        component.showTab('history');
        fixture.detectChanges();
        const [card] = cards();

        findButton(card, 'הצג תוכן ההודעה')!.click();
        fixture.detectChanges();

        expect(reportServiceMock.getReport).toHaveBeenCalledWith('report-dm-8');
        expect(card.textContent).toContain('ההודעה שהוסרה');
      });
    });
  });

  describe('the history tab', () => {
    it('does not fetch history before the tab is opened', () => {
      expect(reportServiceMock.getReportHistory).not.toHaveBeenCalled();
    });

    it('reaches the next tab with the arrow keys, and focuses it', () => {
      const historyTab: HTMLElement = root().querySelector('#tab-history')!;

      component.moveToTab(new KeyboardEvent('keydown', { key: 'ArrowRight' }), tabButtons());

      expect(component.activeTab()).toBe('history');
      expect(document.activeElement).toBe(historyTab);
    });

    it('leaves other keys to the browser', () => {
      component.moveToTab(new KeyboardEvent('keydown', { key: 'Tab' }), tabButtons());

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

      expect(text()).toContain('הדיווח התקבל');
      expect(text()).toContain('תוכן פוגעני');
      expect(text()).toContain('מחוק');
      expect(text()).toContain('16/07/2026');
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
      fixture.detectChanges();

      expect(component.historyError()).toBe(true);
      expect(component.isHistoryLoading()).toBe(false);
      expect(text()).toContain('אירעה שגיאה בטעינת ההיסטוריה');
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

    /** A decided report is read back on the same screen, decision and all. */
    it('opens a decided report in full too', () => {
      component.showTab('history');
      fixture.detectChanges();
      const link: HTMLAnchorElement = root().querySelector('.reports__detail-link')!;

      expect(link.getAttribute('href')).toBe('/moderator/reports/report-9');
    });

    it('reports an empty history rather than showing nothing', () => {
      reportServiceMock.getReportHistory.mockReturnValue(
        of(makeHistoryPage({ items: [], total: 0 })),
      );

      component.showTab('history');
      fixture.detectChanges();

      expect(text()).toContain('עדיין לא התקבלו החלטות');
    });
  });

  /**
   * ABF-116's half of this screen: the restrictions §7.2 applied by itself.
   *
   * Read-only on purpose — there is no control here that lifts one — so what
   * these pin is that the right rows arrive, that they arrive when the tab is
   * opened rather than on every page load, and that a decision taken in the
   * queue makes them stale.
   */
  describe('the restrictions tab', () => {
    it('does not fetch restrictions before the tab is opened', () => {
      expect(reportServiceMock.getActiveRestrictions).not.toHaveBeenCalled();
    });

    it('loads them the first time the tab is opened', () => {
      component.showTab('restrictions');

      expect(reportServiceMock.getActiveRestrictions).toHaveBeenCalledOnce();
      expect(component.restrictions().length).toBe(1);
      expect(component.isRestrictionsLoading()).toBe(false);
      expect(component.restrictionsError()).toBe(false);
    });

    it('does not fetch them again while nothing has been decided', () => {
      component.showTab('restrictions');
      component.showTab('pending');
      component.showTab('restrictions');

      expect(reportServiceMock.getActiveRestrictions).toHaveBeenCalledOnce();
    });

    it('re-reads them after a decision, which is what can apply one', () => {
      component.showTab('restrictions');
      component.showTab('pending');

      component.decide(makeReport(), ReportDecision.VALID);
      component.confirmDecision('הערה מנומקת');
      component.showTab('restrictions');

      expect(reportServiceMock.getActiveRestrictions).toHaveBeenCalledTimes(2);
    });

    it('names the restricted member, the measure and when it ends', () => {
      component.showTab('restrictions');
      fixture.detectChanges();
      const card = cards()[0];
      const row = makeRestrictions().items[0];

      expect(card.querySelector('.reports__title')!.textContent!.trim()).toBe('Dana Levi');
      expect(card.querySelector('.badge--alert')!.textContent!.trim()).toBe('שליחת הודעות פרטיות');
      expect(fieldsOf(card)).toContain(`בתוקף עד: ${wallClock(row.expires_at)}`);
      expect(fieldsOf(card)).toContain(`הופעלה בתאריך: ${wallClock(row.created_at)}`);
    });

    /**
     * Both dates arrive as naive UTC — `2026-07-18T09:30:00`, no offset — and
     * the date pipe reads a string without one as a *local* wall clock. Left
     * raw, the column tells a moderator in Israel that a restriction runs
     * until 09:30 when it in fact lifts at 12:30, and the same three hours are
     * off the date it was applied. utc-date.util.ts exists for this; the chat
     * screen already states this very timestamp to the restricted member
     * through it.
     *
     * Asserted on the instant rather than on rendered text on purpose: CI runs
     * in UTC, where the bug is invisible, so a rendered-string assertion would
     * pass either way and guard nothing.
     */
    it('states both dates as UTC, not as a local wall clock', () => {
      component.showTab('restrictions');
      const row = component.restrictions()[0];

      expect(component.endsAt(row)).toBe('2026-07-18T09:30:00Z');
      expect(new Date(component.endsAt(row)).toISOString()).toBe('2026-07-18T09:30:00.000Z');
      expect(component.appliedAt(row)).toBe('2026-07-16T09:30:00Z');
      expect(new Date(component.appliedAt(row)).toISOString()).toBe('2026-07-16T09:30:00.000Z');
    });

    /**
     * The count and the window move to different places in the sentence
     * between Hebrew and English, so they are two parameters of one key
     * rather than text either side of a number (ABF-131).
     */
    it('says why, from one key with the count and the window as parameters', () => {
      component.showTab('restrictions');
      const transloco = TestBed.inject(TranslocoService);

      transloco.setTranslationKey(
        'moderator.restrictions.reason_value_messaging',
        '{{days}} ימים, {{count}} דיווחים',
        { lang: 'he' },
      );
      fixture.detectChanges();

      expect(fieldsOf(cards()[0])).toContain('הסיבה: 30 ימים, 3 דיווחים');
    });

    /**
     * The two kinds of row carry the same `report_count` and it means opposite
     * things: on a messaging restriction the reports were upheld *against* the
     * member, on a reporting one they are her own reports that were dismissed.
     * One shared sentence — which is what this screen first shipped with —
     * told the moderator that a member whose reports keep being thrown out had
     * five reports upheld against her, which is the reverse of the truth.
     */
    it('says why a reporting restriction was applied without calling it upheld', async () => {
      await render({ restrictions: of(makeReportingRestrictions()) });
      component.showTab('restrictions');
      fixture.detectChanges();
      const card = cards()[0];

      expect(card.querySelector('.badge--alert')!.textContent!.trim()).toBe('מכסת דיווחים יומית');
      expect(fieldsOf(card)).toContain('הסיבה: 5 דיווחים שהגישה נמצאו שגויים ב-30 הימים האחרונים');
      expect(fieldsOf(card).join(' ')).not.toContain('מוצדקים');

      switchToEnglish();

      expect(fieldsOf(cards()[0])).toContain(
        'Reason: 5 reports she filed were dismissed in the last 30 days',
      );
      expect(fieldsOf(cards()[0]).join(' ')).not.toContain('upheld');
    });

    /** The other kind still reads as what it is, in both catalogues. */
    it('says a messaging restriction was upheld against her', () => {
      component.showTab('restrictions');
      fixture.detectChanges();

      expect(fieldsOf(cards()[0])).toContain(
        'הסיבה: 3 דיווחים עליה נמצאו מוצדקים ב-30 הימים האחרונים',
      );

      switchToEnglish();

      expect(fieldsOf(cards()[0])).toContain(
        'Reason: 3 reports about her were upheld in the last 30 days',
      );
      expect(text()).not.toMatch(HEBREW);
    });

    it('shows nothing but the member — no report content, no reporter', () => {
      component.showTab('restrictions');
      fixture.detectChanges();

      expect(cards()[0].querySelector('.reports__content')).toBeNull();
      expect(text()).not.toContain('תוכן ההודעה שדווחה');
      expect(text()).not.toContain('user-1');
    });

    it('reports an empty list rather than showing nothing', async () => {
      await render({ restrictions: of({ items: [], total: 0 }) });

      component.showTab('restrictions');
      fixture.detectChanges();

      expect(text()).toContain('אין הגבלות פעילות');
    });

    it('shows a loading state while the list is in flight', async () => {
      await render({ restrictions: NEVER });

      component.showTab('restrictions');
      fixture.detectChanges();

      expect(component.isRestrictionsLoading()).toBe(true);
      expect(text()).toContain('טוען הגבלות');
    });

    it('shows an error state when the list cannot be loaded', async () => {
      await render({ restrictions: throwError(() => new Error('boom')) });

      component.showTab('restrictions');
      fixture.detectChanges();

      expect(component.restrictionsError()).toBe(true);
      expect(text()).toContain('אירעה שגיאה בטעינת ההגבלות');
    });

    /**
     * A moderator using a screen reader otherwise hears silence and cannot
     * tell an empty list from one that never arrived. app-error-display
     * carries its own role="alert"; the spinner and the empty line have
     * nothing of their own, which is what the wrapper is for.
     */
    it('announces its loading, empty and error states', async () => {
      await render({ restrictions: NEVER });
      component.showTab('restrictions');
      fixture.detectChanges();
      const live = () => root().querySelector('[aria-live="polite"]')!;

      expect(live().getAttribute('aria-busy')).toBe('true');
      expect(live().textContent).toContain('טוען הגבלות');

      await render({ restrictions: of({ items: [], total: 0 }) });
      component.showTab('restrictions');
      fixture.detectChanges();

      expect(live().getAttribute('aria-busy')).toBe('false');
      expect(live().textContent).toContain('אין הגבלות פעילות');

      await render({ restrictions: throwError(() => new Error('boom')) });
      component.showTab('restrictions');
      fixture.detectChanges();

      expect(live().querySelector('[role="alert"]')!.textContent).toContain(
        'אירעה שגיאה בטעינת ההגבלות',
      );
    });

    it('wraps to the last tab on ArrowLeft from the first', () => {
      component.moveToTab(new KeyboardEvent('keydown', { key: 'ArrowLeft' }), tabButtons());

      expect(component.activeTab()).toBe('restrictions');
      expect(document.activeElement).toBe(root().querySelector('#tab-restrictions'));
    });
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as the screen was written', () => {
      expect(heading()).toBe('לוח בקרת מבקר');
      expect(tabLabels()).toEqual(['דיווחים ממתינים 1', 'היסטוריה', 'הגבלות פעילות']);
      expect(fieldsOf(cards()[0])).toEqual([
        'סיבת הדיווח: הטרדה',
        'פירוט המדווח/ת: התבטאות פוגענית',
        'תאריך הדיווח: 15/07/2026 09:30',
        'מצב ההודעה: גלוי',
      ]);
      expect(actionLabels()).toEqual([
        'פרטי דיווח',
        'מחיקת ההודעה (מוצדק)',
        'ביטול הדיווח (שגוי)',
        'כרטיס המשתמש/ת',
      ]);
    });

    it('leaves no Hebrew on the pending queue in English', async () => {
      await render({ pending: of({ items: [makeLatinReport()], total: 1, pending_count: 1 }) });

      switchToEnglish();

      expect(heading()).toBe('Moderator dashboard');
      expect(fieldsOf(cards()[0])).toEqual([
        'Report reason: Harassment',
        'What the reporter wrote: The author is swearing',
        'Report date: 15/07/2026 09:30',
        'Message status: Visible',
      ]);
      expect(actionLabels()).toEqual([
        'Report details',
        'Delete the message (valid)',
        'Dismiss the report (invalid)',
        'User card',
      ]);
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The sweep above reads `textContent`, which an `aria-label` is not part
     * of — a screen reader would have gone on reading Hebrew on an English
     * page and nothing would have said so. Three of them on this screen name
     * the reported post, so they are also the parameters check.
     */
    it('translates the aria-labels, which the text sweep cannot see', async () => {
      await render({ pending: of({ items: [makeLatinReport()], total: 1, pending_count: 1 }) });

      expect(ariaLabels()).toEqual([
        'דיווחים',
        'פרטי הדיווח על ״A post about the paperwork״',
        'מחיקת ההודעה ״A post about the paperwork״',
        'ביטול הדיווח על ״A post about the paperwork״',
        'כרטיס המשתמש/ת שכתב/ה את ״A post about the paperwork״',
      ]);

      switchToEnglish();

      expect(ariaLabels()).toEqual([
        'Reports',
        'Details of the report about “A post about the paperwork”',
        'Delete the message “A post about the paperwork”',
        'Dismiss the report about “A post about the paperwork”',
        'Card of the user who wrote “A post about the paperwork”',
      ]);
      expect(ariaLabels().join(' ')).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the empty state in English', async () => {
      await render({ pending: of({ items: [], total: 0, pending_count: 0 }) });

      switchToEnglish();

      expect(text()).toContain('No pending reports. Nice work!');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the page while the list is still loading', async () => {
      await render({ pending: NEVER });
      expect(text()).toContain('טוען דיווחים...');

      switchToEnglish();

      expect(root().querySelector('app-loading-spinner')).toBeTruthy();
      expect(text()).toContain('Loading reports...');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the failure in English, and re-renders it', async () => {
      await render({ pending: throwError(() => ({})) });
      expect(text()).toContain('אירעה שגיאה בטעינת הדיווחים.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong loading the reports.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the history tab in English', async () => {
      await render({
        pending: of({ items: [makeLatinReport()], total: 1, pending_count: 1 }),
        history: of(
          makeHistoryPage({
            items: [
              makeLatinReport({
                id: 'report-9',
                decision: ReportDecision.VALID,
                moderator_note: 'Offensive content',
                decided_at: '2026-07-16T10:00:00',
                content_status: PostStatus.DELETED,
              }),
            ],
            total: 5,
            page: 2,
            page_size: 2,
          }),
        ),
      });
      component.showTab('history');
      fixture.detectChanges();
      expect(text()).toContain('הדיווח התקבל');
      expect(text()).toContain('עמוד 2 מתוך 3');

      switchToEnglish();

      expect(text()).toContain('Report upheld');
      expect(text()).toContain('Page 2 of 3');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders an action failure of ours in the new language', () => {
      reportServiceMock.decideReport.mockReturnValue(throwError(() => ({ error: null })));
      component.decide(makeLatinReport(), ReportDecision.VALID);
      component.confirmDecision('Offensive content');
      fixture.detectChanges();
      expect(text()).toContain('אירעה שגיאה בשמירת ההחלטה. נסי שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong saving the decision.');
    });

    /**
     * A sentence the server wrote is shown as it came, in either UI language:
     * swallowing it would cost the reader the one thing our generic line
     * cannot tell them, which is *why* the request failed (ABF-129).
     */
    it('leaves a failure the server worded alone', () => {
      reportServiceMock.decideReport.mockReturnValue(
        throwError(() => ({ error: { detail: 'הדיווח כבר טופל.' } })),
      );
      component.decide(makeReport(), ReportDecision.VALID);
      component.confirmDecision('תוכן פוגעני');
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('הדיווח כבר טופל.');
    });

    it('translates the confirmation dialog through the caller, not the dialog', () => {
      component.decide(makeLatinReport(), ReportDecision.VALID);
      fixture.detectChanges();
      const dialog = (): HTMLElement => root().querySelector('app-confirm-dialog')!;
      expect(dialog().textContent).toContain('מחיקת ההודעה');
      expect(dialog().textContent).toContain('הערת המבקר/ת (חובה)');

      switchToEnglish();

      expect(dialog().textContent).toContain('Delete the message');
      expect(dialog().textContent).toContain("Moderator's note (required)");
      expect(dialog().textContent).not.toMatch(HEBREW);
      expect(dialog().querySelector('textarea')!.getAttribute('placeholder')).not.toMatch(HEBREW);
    });

    /**
     * The reason, the content status and the decision are shared label maps
     * (ABF-127). This module renders them through the pipe and adds no key of
     * its own for them — the renames below are what a private copy would hide.
     */
    it('takes the reason, the status and the decision from the shared constants', () => {
      const transloco = TestBed.inject(TranslocoService);

      transloco.setTranslationKey('constants.report_reason.harassment', 'מילה אחרת', {
        lang: 'he',
      });
      transloco.setTranslationKey('constants.post_status.visible', 'מצב אחר', { lang: 'he' });
      transloco.setTranslationKey('constants.report_decision.valid', 'הכרעה אחרת', { lang: 'he' });
      component.showTab('history');
      fixture.detectChanges();
      expect(text()).toContain('הכרעה אחרת');

      component.showTab('pending');
      fixture.detectChanges();

      expect(fieldsOf(cards()[0])).toContain('סיבת הדיווח: מילה אחרת');
      expect(fieldsOf(cards()[0])).toContain('מצב ההודעה: מצב אחר');
    });

    /**
     * "2 דיווחים" and "2 reports" happen to put the number in the same place,
     * but a wording that did not would need it to move inside the sentence —
     * which two separate text nodes cannot do (ABF-131).
     */
    it('builds the counter from one key with the count as a parameter', async () => {
      await render({
        pending: of({ items: [makeReport({ report_count: 12 })], total: 1, pending_count: 1 }),
      });
      const transloco = TestBed.inject(TranslocoService);

      transloco.setTranslationKey('moderator.reports.report_count', 'סך הכול {{count}}', {
        lang: 'he',
      });
      fixture.detectChanges();

      expect(root().querySelector('.badge--alert')!.textContent!.trim()).toBe('סך הכול 12');
    });

    /**
     * The reported post and the reporter's own words are user content: they
     * stay in the language they were written in, in either UI language
     * (ABF-130).
     */
    it('leaves the reported content in the language it was written in', () => {
      switchToEnglish();

      expect(cards()[0].querySelector('.reports__title')!.textContent!.trim()).toBe('כותרת ההודעה');
      expect(fieldsOf(cards()[0])).toContain('What the reporter wrote: התבטאות פוגענית');
    });

    /**
     * A dash is a glyph, not copy — it reads the same in both languages and is
     * Bidi-neutral, so it stays out of the translation files. Same call the
     * dashboard chevron got in ABF-132.
     */
    it('keeps the empty-description dash as a glyph in either language', async () => {
      await render({
        pending: of({
          items: [makeLatinReport({ description: null })],
          total: 1,
          pending_count: 1,
        }),
      });
      expect(fieldsOf(cards()[0])).toContain('פירוט המדווח/ת: –');

      switchToEnglish();

      expect(fieldsOf(cards()[0])).toContain('What the reporter wrote: –');
      expect(text()).not.toMatch(HEBREW);
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      const page = root().querySelector('.page') as HTMLElement;

      expect(root().hasAttribute('dir')).toBe(false);
      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });

    /**
     * A <button> with no type is type="submit". None of these submit anything,
     * and the moment one lands inside a <form> the default would submit it
     * instead of running the click handler. CONTRIBUTING §5 asks for
     * type="button" always.
     */
    it('gives every button an explicit type="button"', () => {
      const buttons = [...root().querySelectorAll('button')];

      expect(buttons.length).toBeGreaterThan(0);
      expect(buttons.every((button) => button.getAttribute('type') === 'button')).toBe(true);
    });
  });
});
