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
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

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

/**
 * A report whose reported content carries no Hebrew.
 *
 * The post's title, its body and the words the reporter typed are
 * user-generated content — never translated (ABF-130). Feeding Latin content
 * to the `HEBREW` sweeps below keeps them pointed at our own copy, which is
 * the thing they are meant to guard.
 */
function makeLatinReport(overrides: Partial<ReportWithContent> = {}): ReportWithContent {
  return makeReport({
    content_title: 'A post about the paperwork',
    content_text: 'Body text',
    description: 'The author is swearing',
    ...overrides,
  });
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

  /** Builds the screen; `pending` and `history` override the default fixtures. */
  async function render({
    pending = of({ items: [makeReport()], total: 1, pending_count: 1 }),
    history = of(makeHistoryPage()),
  }: { pending?: unknown; history?: unknown } = {}): Promise<void> {
    TestBed.resetTestingModule();

    reportServiceMock = {
      getPendingReports: vi.fn().mockReturnValue(pending),
      getReportHistory: vi.fn().mockReturnValue(history),
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

    it('opens the way through to the card of the reported user', () => {
      const link: HTMLAnchorElement = root().querySelector('.reports__card-link')!;

      expect(link.getAttribute('href')).toBe('/moderator/users/user-2');
      expect(link.getAttribute('aria-label')).toContain('כותרת ההודעה');
    });

    it('sets hasError when the queue fails to load', async () => {
      await render({ pending: throwError(() => ({})) });

      expect(component.hasError()).toBe(true);
      expect(component.isLoading()).toBe(false);
      expect(root().querySelector('app-error-display')).toBeTruthy();
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

  describe('the history tab', () => {
    it('does not fetch history before the tab is opened', () => {
      expect(reportServiceMock.getReportHistory).not.toHaveBeenCalled();
    });

    it('reaches the unselected tab with the arrow keys, and focuses it', () => {
      const historyTab: HTMLElement = root().querySelector('#tab-history')!;

      component.moveToTab(
        new KeyboardEvent('keydown', { key: 'ArrowLeft' }),
        'history',
        historyTab,
      );

      expect(component.activeTab()).toBe('history');
      expect(document.activeElement).toBe(historyTab);
    });

    it('leaves other keys to the browser', () => {
      const historyTab: HTMLElement = root().querySelector('#tab-history')!;

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

    it('reports an empty history rather than showing nothing', () => {
      reportServiceMock.getReportHistory.mockReturnValue(
        of(makeHistoryPage({ items: [], total: 0 })),
      );

      component.showTab('history');
      fixture.detectChanges();

      expect(text()).toContain('עדיין לא התקבלו החלטות');
    });
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as the screen was written', () => {
      expect(heading()).toBe('לוח בקרת מבקר');
      expect(tabLabels()).toEqual(['דיווחים ממתינים 1', 'היסטוריה']);
      expect(fieldsOf(cards()[0])).toEqual([
        'סיבת הדיווח: הטרדה',
        'פירוט המדווח/ת: התבטאות פוגענית',
        'תאריך הדיווח: 15/07/2026 09:30',
        'מצב ההודעה: גלוי',
      ]);
      expect(actionLabels()).toEqual([
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
        'מחיקת ההודעה ״A post about the paperwork״',
        'ביטול הדיווח על ״A post about the paperwork״',
        'כרטיס המשתמש/ת שכתב/ה את ״A post about the paperwork״',
      ]);

      switchToEnglish();

      expect(ariaLabels()).toEqual([
        'Reports',
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
