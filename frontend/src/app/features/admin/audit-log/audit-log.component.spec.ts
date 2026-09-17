/**
 * The audit log viewer (ABF-152).
 *
 * The screen replaces a stub whose only real UI was a heading and a back
 * link, and whose spec pinned those two through a language switch (ABF-131's
 * treatment, carried here). Those i18n guards stay, because the screen that
 * replaced the stub is the screen they were written for — and they are joined
 * by the four things this one has to get right:
 *
 *   `the table`      — real rows, from the service, in the four columns the
 *                      ticket names, with the `when` column read as UTC.
 *   `the filters`    — typing changes nothing until Apply, two filters travel
 *                      together, and clearing really clears.
 *   `sorting/paging` — both directions reach the server, page 1 is restored
 *                      whenever the ordering or the filters change, and the
 *                      pager agrees with the page the server answered with.
 *   `the states`     — loading, empty (and *which* empty), and an error that
 *                      does not leave an empty table claiming the log is bare.
 *
 * Nothing here asserts on an IP address, because there is nothing to assert
 * on: the response has no such field. What is asserted is that a server which
 * sent one anyway would still not get it onto the screen.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AuditLogComponent } from './audit-log.component';
import { AuditAction } from '../../../core/constants';
import type { AuditLogEntry, AuditLogList } from '../../../core/models';
import { ReportService } from '../../../core/services/report.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

/**
 * An entry whose every free-text field is Latin.
 *
 * Actor ids, entity types and entity ids are identifiers the server stored —
 * content, never translated (ABF-130). Keeping them Latin is what leaves the
 * `HEBREW` sweep below pointed at our own copy, which is what it is for.
 */
function makeEntry(overrides: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: 'entry-1',
    actor_id: 'admin-0001',
    action_type: AuditAction.USER_APPROVED,
    entity_type: 'User',
    entity_id: 'user-0009',
    timestamp: '2026-09-01T12:00:00',
    details: null,
    ...overrides,
  };
}

function makePage(overrides: Partial<AuditLogList> = {}): AuditLogList {
  return {
    items: [makeEntry()],
    total_count: 1,
    page: 1,
    page_size: 50,
    ...overrides,
  };
}

/**
 * A naive-UTC timestamp as this runner's clock renders it, in the screen's
 * `dd/MM/yyyy HH:mm`.
 *
 * Derived rather than hardcoded: the column shows the instant in the admin's
 * own zone, so the digits differ between CI (UTC) and a machine in Israel
 * (UTC+3). A literal would pin one of the two and fail on the other — the
 * same reason reports.component.spec.ts derives its own.
 */
function wallClock(naiveUtc: string): string {
  const at = new Date(`${naiveUtc}Z`);
  const pad = (value: number): string => String(value).padStart(2, '0');
  return (
    `${pad(at.getDate())}/${pad(at.getMonth() + 1)}/${at.getFullYear()} ` +
    `${pad(at.getHours())}:${pad(at.getMinutes())}`
  );
}

describe('AuditLogComponent', () => {
  let fixture: ComponentFixture<AuditLogComponent>;
  let reportServiceMock: { getAuditLog: ReturnType<typeof vi.fn> };

  async function render(log: unknown = of(makePage())): Promise<void> {
    TestBed.resetTestingModule();

    reportServiceMock = { getAuditLog: vi.fn().mockReturnValue(log) };

    await TestBed.configureTestingModule({
      imports: [AuditLogComponent, translocoTesting()],
      providers: [{ provide: ReportService, useValue: reportServiceMock }, provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(AuditLogComponent);
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await render();
  });

  // ---------------------------------------------------------------------------
  // Reading the page
  // ---------------------------------------------------------------------------

  function root(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return root().textContent ?? '';
  }

  function heading(): string {
    return root().querySelector('h1')!.textContent!.trim();
  }

  function table(): HTMLTableElement | null {
    return root().querySelector('table');
  }

  function headers(): string[] {
    return [...root().querySelectorAll('thead th')].map((th) => th.textContent!.trim());
  }

  function rows(): HTMLElement[] {
    return [...root().querySelectorAll<HTMLElement>('tbody tr')];
  }

  function cells(rowIndex = 0): string[] {
    return [...rows()[rowIndex].querySelectorAll('td')].map((td) => td.textContent!.trim());
  }

  function input(name: string): HTMLInputElement {
    return root().querySelector<HTMLInputElement>(`input[name="${name}"]`)!;
  }

  function actionSelect(): HTMLSelectElement {
    return root().querySelector<HTMLSelectElement>('select[name="action_type"]')!;
  }

  function buttonWith(label: string): HTMLButtonElement {
    return [...root().querySelectorAll<HTMLButtonElement>('button')].find((button) =>
      button.textContent!.includes(label),
    )!;
  }

  function sortHeaderButton(): HTMLButtonElement {
    return root().querySelector<HTMLButtonElement>('.audit-log__sort')!;
  }

  // ---------------------------------------------------------------------------
  // Driving it
  // ---------------------------------------------------------------------------

  function type(name: string, value: string): void {
    const box = input(name);
    box.value = value;
    box.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  function choose(action: AuditAction | ''): void {
    const select = actionSelect();
    select.value = action;
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
  }

  function apply(): void {
    root().querySelector('form')!.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
  }

  function lastQuery(): Record<string, unknown> {
    const calls = reportServiceMock.getAuditLog.mock.calls;
    return calls[calls.length - 1][0] as Record<string, unknown>;
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  // ---------------------------------------------------------------------------
  // The table
  // ---------------------------------------------------------------------------

  describe('the table', () => {
    it('fetches the first page on open', () => {
      expect(reportServiceMock.getAuditLog).toHaveBeenCalledTimes(1);
      expect(lastQuery()).toMatchObject({ page: 1 });
    });

    it('renders a real table, not the stub it replaced', () => {
      expect(table()).not.toBeNull();
      expect(text()).not.toContain('TODO');
    });

    it('gives it the four columns the ticket names', () => {
      const [who, what] = headers();

      expect(who).toBe('מי');
      expect(what).toBe('מה');
      // The `when` header is a button, so its text carries the sort glyph too.
      expect(headers()[2]).toContain('מתי');
      expect(headers()[3]).toBe('ישות');
    });

    it('puts one row on screen per entry the server sent', async () => {
      await render(
        of(
          makePage({
            items: [makeEntry({ id: 'a' }), makeEntry({ id: 'b' }), makeEntry({ id: 'c' })],
            total_count: 3,
          }),
        ),
      );

      expect(rows()).toHaveLength(3);
    });

    it('shows who did it, what they did, when, and to which entity', () => {
      const [who, what, when, entity] = cells();

      expect(who).toBe('admin-0001');
      expect(what).toBe('אישור הרשמה');
      expect(when).toBe(wallClock('2026-09-01T12:00:00'));
      expect(entity).toContain('User');
      expect(entity).toContain('user-0009');
    });

    /**
     * The timestamp arrives as naive UTC, and both `new Date()` and the date
     * pipe read a string with no offset as a *local* wall clock. Read
     * straight through, every row of an audit log would name an instant three
     * hours off in Israel — on a record that may be read back in a legal
     * proceeding.
     */
    it('reads the timestamp as UTC, not as a local wall clock', async () => {
      await render(of(makePage({ items: [makeEntry({ timestamp: '2026-09-01T23:30:00' })] })));

      expect(cells()[2]).toBe(wallClock('2026-09-01T23:30:00'));
    });

    /**
     * The `what` column falls back to the wire value for an action this build
     * has no label for. An audit row that silently omits what happened is
     * worse than one that says `some_future_action`.
     */
    it('falls back to the raw action for a value it has no label for', async () => {
      await render(
        of(
          makePage({
            items: [makeEntry({ action_type: 'some_future_action' as AuditAction })],
          }),
        ),
      );

      expect(cells()[1]).toBe('some_future_action');
    });

    it('says how many entries matched, not how many are on this page', async () => {
      await render(of(makePage({ items: [makeEntry()], total_count: 412 })));

      expect(text()).toContain('412');
    });

    /**
     * The API does not send `ip_address` and never will. This pins the other
     * half of that promise: a server that sent one anyway — a rolled-back
     * deploy, a proxy that rewrote the body — still could not put it on an
     * admin's screen, because nothing in the template reaches for it.
     */
    it('puts no IP address on screen even if the response carries one', async () => {
      await render(
        of(
          makePage({
            items: [{ ...makeEntry(), ip_address: '203.0.113.7' } as AuditLogEntry],
          }),
        ),
      );

      expect(text()).not.toContain('203.0.113.7');
    });
  });

  // ---------------------------------------------------------------------------
  // Filters
  // ---------------------------------------------------------------------------

  describe('the filters', () => {
    it('does not refetch on a keystroke', () => {
      type('actor_id', 'admin-0001');

      expect(reportServiceMock.getAuditLog).toHaveBeenCalledTimes(1);
    });

    it('sends the filter once it is applied', () => {
      type('actor_id', 'admin-0001');
      apply();

      expect(lastQuery()).toMatchObject({ actor_id: 'admin-0001' });
    });

    /**
     * The acceptance criterion in its own words: two filters at once return
     * their intersection. On this side that means both of them leave in one
     * request — a screen that forgot one would be showing the intersection of
     * the other with everything.
     */
    it('sends two filters together, not one of them', () => {
      type('actor_id', 'admin-0001');
      choose(AuditAction.POST_DELETED);
      apply();

      expect(lastQuery()).toMatchObject({
        actor_id: 'admin-0001',
        action_type: AuditAction.POST_DELETED,
      });
    });

    it('sends every filter the panel offers', () => {
      type('actor_id', 'admin-0001');
      choose(AuditAction.POST_DELETED);
      type('entity_type', 'ForumPost');
      type('entity_id', 'post-3');
      type('date_from', '2026-09-01');
      type('date_to', '2026-09-30');
      apply();

      expect(lastQuery()).toMatchObject({
        actor_id: 'admin-0001',
        action_type: AuditAction.POST_DELETED,
        entity_type: 'ForumPost',
        entity_id: 'post-3',
        date_from: '2026-09-01',
        date_to: '2026-09-30',
      });
    });

    it('leaves an untouched filter out of the request entirely', () => {
      type('actor_id', 'admin-0001');
      apply();

      expect(lastQuery()).not.toHaveProperty('entity_id');
      expect(lastQuery()).not.toHaveProperty('date_from');
    });

    /**
     * Page 4 of the unfiltered log is very unlikely to exist under a new
     * filter, and landing on an empty page reads as "nothing matched" when
     * page 1 was full of matches.
     */
    it('goes back to page 1 when a filter is applied', async () => {
      await render(of(makePage({ items: [makeEntry()], total_count: 200, page: 1 })));
      reportServiceMock.getAuditLog.mockReturnValue(
        of(makePage({ items: [makeEntry()], total_count: 200, page: 2 })),
      );
      buttonWith('הבא').click();
      fixture.detectChanges();
      expect(lastQuery()).toMatchObject({ page: 2 });

      type('actor_id', 'admin-0001');
      apply();

      expect(lastQuery()).toMatchObject({ page: 1 });
    });

    it('clears every box and refetches unfiltered', () => {
      type('actor_id', 'admin-0001');
      choose(AuditAction.POST_DELETED);
      apply();

      buttonWith('ניקוי סינון').click();
      fixture.detectChanges();

      expect(input('actor_id').value).toBe('');
      expect(actionSelect().value).toBe('');
      expect(lastQuery()).not.toHaveProperty('actor_id');
      expect(lastQuery()).not.toHaveProperty('action_type');
    });

    it('offers every action the platform records', () => {
      const options = [...actionSelect().options].map((option) => option.value);

      // The blank first option is "any action", not an action.
      expect(options[0]).toBe('');
      for (const action of Object.values(AuditAction)) {
        expect(options).toContain(action);
      }
    });
  });

  // ---------------------------------------------------------------------------
  // Sorting
  // ---------------------------------------------------------------------------

  describe('sorting', () => {
    it('starts newest first', () => {
      expect(lastQuery()).toMatchObject({ direction: 'desc' });
      expect(root().querySelector('th[aria-sort]')!.getAttribute('aria-sort')).toBe('descending');
    });

    it('asks the server for the other direction when the header is clicked', () => {
      sortHeaderButton().click();
      fixture.detectChanges();

      expect(lastQuery()).toMatchObject({ direction: 'asc' });
      expect(root().querySelector('th[aria-sort]')!.getAttribute('aria-sort')).toBe('ascending');
    });

    it('flips back on a second click', () => {
      sortHeaderButton().click();
      fixture.detectChanges();
      sortHeaderButton().click();
      fixture.detectChanges();

      expect(lastQuery()).toMatchObject({ direction: 'desc' });
    });

    /**
     * Reversing the order while staying on page 3 keeps the offset and
     * changes what sits under it, dropping the reader into the middle of the
     * log at a place corresponding to nothing they were looking at.
     */
    it('goes back to page 1 when the order is reversed', async () => {
      await render(of(makePage({ items: [makeEntry()], total_count: 200, page: 1 })));
      reportServiceMock.getAuditLog.mockReturnValue(
        of(makePage({ items: [makeEntry()], total_count: 200, page: 2 })),
      );
      buttonWith('הבא').click();
      fixture.detectChanges();

      sortHeaderButton().click();
      fixture.detectChanges();

      expect(lastQuery()).toMatchObject({ page: 1, direction: 'asc' });
    });

    /**
     * A `<th>` is neither focusable nor announced as operable, so a click
     * handler on the cell itself would leave a keyboard reader with no way to
     * sort at all.
     */
    it('sorts from a real button, reachable by keyboard', () => {
      expect(sortHeaderButton().tagName).toBe('BUTTON');
      expect(sortHeaderButton().getAttribute('aria-label')).toBeTruthy();
    });
  });

  // ---------------------------------------------------------------------------
  // Paging
  // ---------------------------------------------------------------------------

  describe('paging', () => {
    async function renderTwoPages(): Promise<void> {
      await render(of(makePage({ items: [makeEntry()], total_count: 60, page: 1 })));
    }

    it('hides the pager when everything fits on one page', () => {
      expect(root().querySelector('.pager')).toBeNull();
    });

    it('shows the pager once there is more than one page', async () => {
      await renderTwoPages();

      expect(root().querySelector('.pager')).not.toBeNull();
      expect(text()).toContain('עמוד 1 מתוך 2');
    });

    it('asks for page 2', async () => {
      await renderTwoPages();

      buttonWith('הבא').click();

      expect(lastQuery()).toMatchObject({ page: 2 });
    });

    it('trusts the page the server answered with, not the one it asked for', async () => {
      await renderTwoPages();
      reportServiceMock.getAuditLog.mockReturnValue(
        of(makePage({ items: [makeEntry({ id: 'other' })], total_count: 60, page: 2 })),
      );

      buttonWith('הבא').click();
      fixture.detectChanges();

      expect(text()).toContain('עמוד 2 מתוך 2');
    });

    it('will not step past either end', async () => {
      await renderTwoPages();

      expect(buttonWith('הקודם').disabled).toBe(true);

      reportServiceMock.getAuditLog.mockReturnValue(
        of(makePage({ items: [makeEntry()], total_count: 60, page: 2 })),
      );
      buttonWith('הבא').click();
      fixture.detectChanges();

      expect(buttonWith('הבא').disabled).toBe(true);
      expect(buttonWith('הקודם').disabled).toBe(false);
    });

    it('goes back to page 1 from page 2', async () => {
      await renderTwoPages();
      reportServiceMock.getAuditLog.mockReturnValue(
        of(makePage({ items: [makeEntry()], total_count: 60, page: 2 })),
      );
      buttonWith('הבא').click();
      fixture.detectChanges();

      buttonWith('הקודם').click();

      expect(lastQuery()).toMatchObject({ page: 1 });
    });

    /**
     * Two clicks while the first request is still in flight. Without a guard
     * the screen shows whichever response happened to arrive last, under a
     * page number that says something else.
     */
    it('ignores a response that a later request has already superseded', async () => {
      const first = new Subject<AuditLogList>();
      const second = new Subject<AuditLogList>();
      await render(first);

      // A second request goes out while the first is still in flight. The
      // filter panel is the control that is on screen either way.
      reportServiceMock.getAuditLog.mockReturnValue(second);
      apply();

      second.next(makePage({ items: [makeEntry({ actor_id: 'winner' })], page: 2 }));
      fixture.detectChanges();
      first.next(makePage({ items: [makeEntry({ actor_id: 'loser' })], page: 1 }));
      fixture.detectChanges();

      expect(text()).toContain('winner');
      expect(text()).not.toContain('loser');
    });

    it('ignores a failure from a request that has already been superseded', async () => {
      const first = new Subject<AuditLogList>();
      const second = new Subject<AuditLogList>();
      await render(first);

      reportServiceMock.getAuditLog.mockReturnValue(second);
      apply();

      second.next(makePage({ items: [makeEntry({ actor_id: 'winner' })] }));
      fixture.detectChanges();
      first.error({ status: 500 });
      fixture.detectChanges();

      expect(root().querySelector('app-error-display')).toBeNull();
      expect(text()).toContain('winner');
    });
  });

  // ---------------------------------------------------------------------------
  // Loading, empty and failed
  // ---------------------------------------------------------------------------

  describe('the states it can be in', () => {
    it('shows a spinner while the first page is in flight', async () => {
      await render(NEVER);

      expect(root().querySelector('app-loading-spinner')).not.toBeNull();
      expect(table()).toBeNull();
    });

    it('says the log is empty when it is', async () => {
      await render(of(makePage({ items: [], total_count: 0 })));

      expect(table()).toBeNull();
      expect(text()).toContain('יומן הביקורת ריק');
    });

    /**
     * Two emptinesses, two sentences. "The log is empty" shown to an admin
     * who just filtered by an actor id is a false statement about the
     * platform, and sends them looking for a bug that is not there.
     */
    it('says instead that nothing matched, when a filter is what emptied it', async () => {
      await render(of(makePage({ items: [], total_count: 0 })));

      type('actor_id', 'nobody');
      apply();

      expect(text()).toContain('אין רשומות התואמות');
      expect(text()).not.toContain('יומן הביקורת ריק');
    });

    it('shows a real message rather than crashing on an empty result', async () => {
      await render(of(makePage({ items: [], total_count: 0 })));

      expect(root().querySelector('.audit-log__empty')).not.toBeNull();
      expect(root().querySelector('.audit-log__empty')!.textContent!.trim()).not.toBe('');
    });

    it('shows our own message when the request fails without one', async () => {
      await render(throwError(() => ({ status: 500 })));

      expect(root().querySelector('app-error-display')).not.toBeNull();
      expect(text()).toContain('אירעה שגיאה בטעינת יומן הביקורת');
    });

    /** The API's `detail` is a finished sentence and is shown as it came. */
    it('shows the API sentence when the response carried one', async () => {
      await render(throwError(() => ({ status: 403, error: { detail: 'Not allowed here' } })));

      expect(text()).toContain('Not allowed here');
    });

    /**
     * An empty table under the error would read as "the log is empty", which
     * is a different claim, and a wrong one.
     */
    it('shows neither a table nor an empty-log message under an error', async () => {
      await render(throwError(() => ({ status: 500 })));

      expect(table()).toBeNull();
      expect(text()).not.toContain('יומן הביקורת ריק');
    });

    it('clears a previous failure when the next request succeeds', async () => {
      await render(throwError(() => ({ status: 500 })));
      reportServiceMock.getAuditLog.mockReturnValue(of(makePage()));

      apply();

      expect(root().querySelector('app-error-display')).toBeNull();
      expect(table()).not.toBeNull();
    });
  });

  // ---------------------------------------------------------------------------
  // i18n — the guards the stub spec left behind, on the screen that replaced it
  // ---------------------------------------------------------------------------

  describe('i18n', () => {
    it('reads in Hebrew exactly as it did before the keys went in', () => {
      expect(heading()).toBe('יומן פעולות (Audit Log)');
      expect(text()).toContain('חזרה ללוח הבקרה');
    });

    it('leaves no Hebrew on the page in English', () => {
      switchToEnglish();

      expect(heading()).toBe('Audit log');
      expect(text()).toContain('Back to the dashboard');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on an empty page in English', async () => {
      await render(of(makePage({ items: [], total_count: 0 })));

      switchToEnglish();

      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on a failed page in English', async () => {
      await render(throwError(() => ({ status: 500 })));

      switchToEnglish();

      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew in a pager or a filter panel in English', async () => {
      await render(of(makePage({ items: [makeEntry()], total_count: 60 })));

      switchToEnglish();

      expect(text()).toContain('Page 1 of 2');
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The one a reading of the diff will not catch: an `aria-label` that
     * stayed Hebrew while the visible text was translated.
     */
    it('translates the labels only a screen reader hears', () => {
      switchToEnglish();

      const ariaLabels = [...root().querySelectorAll('[aria-label]')].map(
        (element) => element.getAttribute('aria-label')!,
      );

      expect(ariaLabels.length).toBeGreaterThan(0);
      for (const label of ariaLabels) {
        expect(label).not.toMatch(HEBREW);
        expect(label).not.toMatch(/^admin\./);
      }
    });

    it('translates the table column headings', () => {
      switchToEnglish();

      expect(headers()[0]).toBe('Who');
      expect(headers()[1]).toBe('What');
      expect(headers()[2]).toContain('When');
      expect(headers()[3]).toBe('Entity');
    });

    it('translates the action on a row, and follows a language switch', () => {
      expect(cells()[1]).toBe('אישור הרשמה');

      switchToEnglish();

      expect(cells()[1]).toBe('Registration approved');
    });

    it('leaves the identifiers on a row alone in both languages', () => {
      switchToEnglish();

      expect(cells()[0]).toBe('admin-0001');
      expect(cells()[3]).toContain('user-0009');
    });

    /**
     * The heading is longer than the dashboard's link to this page, so the
     * two keep separate keys — sharing one would have edited the Hebrew on
     * one of them (CONTRIBUTING §6, ABF-131).
     */
    it('keeps a heading of its own, not the dashboard link to it', () => {
      const translate = TestBed.inject(TranslocoService);

      expect(translate.translate('admin.audit_log.title')).not.toBe(
        translate.translate('admin.dashboard.nav_audit_log'),
      );
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      const page = root().querySelector('div') as HTMLElement;

      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });
  });
});
