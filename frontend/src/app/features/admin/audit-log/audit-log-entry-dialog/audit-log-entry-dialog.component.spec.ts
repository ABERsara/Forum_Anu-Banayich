/**
 * One audit log entry, in full (ABF-153).
 *
 * Five things the dialog has to get right, in the order the ticket names
 * them and then the ones it implies:
 *
 *   `the record`  — every field of the entry it was opened on, fetched by id,
 *                   and never an IP address even if one arrived.
 *   `details`     — laid out as indented JSON, not the one-line escaped
 *                   string a JSON value turns into when printed as text.
 *   `a modal`     — a real one: named, focus moved in, Tab kept in, Escape,
 *                   the close button and the backdrop all close it.
 *   `the states`  — loading, failed (with a way to try again), loaded.
 *   `i18n`        — both languages, aria-labels included, and the record's
 *                   own identifiers left alone.
 */

import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AuditLogEntryDialogComponent } from './audit-log-entry-dialog.component';
import { AuditAction } from '../../../../core/constants';
import type { AuditLogEntry } from '../../../../core/models';
import { AdminService } from '../../../../core/services/admin.service';
import { HEBREW, translocoTesting } from '../../../../../testing/transloco-testing';

/**
 * A details object shaped the way the services really write one: nested, with
 * a list, a number, a boolean and a null — every shape a flattened string
 * would lose. Latin throughout, so the `HEBREW` sweeps stay pointed at our
 * own copy; Hebrew content gets a test of its own below.
 */
const DETAILS = {
  changes: { title: { from: 'First session', to: 'Second session' } },
  revoked_cells: ['cell-1', 'cell-2'],
  hours: 48,
  automatic: false,
  reason: null,
};

function makeEntry(overrides: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: 'entry-0042',
    actor_id: 'admin-0001',
    action_type: AuditAction.USER_SUSPENDED,
    entity_type: 'User',
    entity_id: 'user-0009',
    timestamp: '2026-09-01T12:34:56',
    details: DETAILS,
    ...overrides,
  };
}

/** The dialog's timestamp as this runner's clock renders it — see the list spec. */
function wallClockToTheSecond(naiveUtc: string): string {
  const at = new Date(`${naiveUtc}Z`);
  const pad = (value: number): string => String(value).padStart(2, '0');
  return (
    `${pad(at.getDate())}/${pad(at.getMonth() + 1)}/${at.getFullYear()} ` +
    `${pad(at.getHours())}:${pad(at.getMinutes())}:${pad(at.getSeconds())}`
  );
}

/** Hosts the dialog the way the audit log does, and counts its `closed`. */
@Component({
  standalone: true,
  imports: [AuditLogEntryDialogComponent],
  template: `<app-audit-log-entry-dialog [entryId]="entryId()" (closed)="closes = closes + 1" />`,
})
class HostComponent {
  readonly entryId = signal('entry-0042');
  closes = 0;
}

describe('AuditLogEntryDialogComponent', () => {
  let fixture: ComponentFixture<HostComponent>;
  let adminServiceMock: { getAuditLogEntry: ReturnType<typeof vi.fn> };

  async function render(response: unknown = of(makeEntry())): Promise<void> {
    TestBed.resetTestingModule();

    adminServiceMock = { getAuditLogEntry: vi.fn().mockReturnValue(response) };

    await TestBed.configureTestingModule({
      imports: [HostComponent, translocoTesting()],
      providers: [{ provide: AdminService, useValue: adminServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(HostComponent);
    // Attached, so that focus() and document.activeElement mean what they
    // mean in a browser — a detached element can be told to focus and never
    // becomes the active one.
    document.body.appendChild(fixture.nativeElement);
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await render();
  });

  afterEach(() => {
    (fixture.nativeElement as HTMLElement).remove();
  });

  // ---------------------------------------------------------------------------
  // Reading it
  // ---------------------------------------------------------------------------

  function root(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return root().textContent ?? '';
  }

  function dialog(): HTMLElement {
    return root().querySelector<HTMLElement>('[role="dialog"]')!;
  }

  function backdrop(): HTMLElement {
    return root().querySelector<HTMLElement>('.entry-dialog')!;
  }

  function details(): HTMLElement | null {
    return root().querySelector<HTMLElement>('.entry-dialog__details');
  }

  /** `<dt>` → `<dd>` text, as the reader pairs them, with the markup's line breaks folded. */
  function fields(): Record<string, string> {
    const terms = [...root().querySelectorAll('dt')];
    return Object.fromEntries(
      terms.map((dt) => [
        dt.textContent!.trim(),
        (dt.nextElementSibling as HTMLElement).textContent!.replace(/\s+/g, ' ').trim(),
      ]),
    );
  }

  function closeButton(): HTMLButtonElement {
    return root().querySelector<HTMLButtonElement>('.entry-dialog__header button')!;
  }

  function buttonWith(label: string): HTMLButtonElement | undefined {
    return [...root().querySelectorAll<HTMLButtonElement>('button')].find((button) =>
      button.textContent!.includes(label),
    );
  }

  function press(key: string, options: KeyboardEventInit = {}): KeyboardEvent {
    const event = new KeyboardEvent('keydown', {
      key,
      bubbles: true,
      cancelable: true,
      ...options,
    });
    (document.activeElement ?? dialog()).dispatchEvent(event);
    fixture.detectChanges();
    return event;
  }

  function closes(): number {
    return fixture.componentInstance.closes;
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  // ---------------------------------------------------------------------------
  // The record
  // ---------------------------------------------------------------------------

  describe('the record', () => {
    it('fetches the entry it was opened on, by id, once', () => {
      expect(adminServiceMock.getAuditLogEntry).toHaveBeenCalledTimes(1);
      expect(adminServiceMock.getAuditLogEntry).toHaveBeenCalledWith('entry-0042');
    });

    it('shows every field of the entry', () => {
      expect(fields()).toEqual({
        פעולה: 'השעיית משתמש/ת user_suspended',
        מתי: wallClockToTheSecond('2026-09-01T12:34:56'),
        'מזהה מבצע/ת': 'admin-0001',
        'סוג ישות': 'User',
        'מזהה ישות': 'user-0009',
        'מזהה רשומה': 'entry-0042',
      });
    });

    /**
     * The timestamp arrives as naive UTC; read as a local wall clock it would
     * be three hours off in Israel, on a record that may be read back in a
     * legal proceeding.
     */
    it('reads the timestamp as UTC, to the second', async () => {
      await render(of(makeEntry({ timestamp: '2026-09-01T23:59:07' })));

      expect(fields()['מתי']).toBe(wallClockToTheSecond('2026-09-01T23:59:07'));
    });

    it('names the action in words and gives its wire value beside it', () => {
      const action = root().querySelector('dd')!;

      expect(action.textContent).toContain('השעיית משתמש');
      expect(action.querySelector('code')!.textContent).toBe('user_suspended');
    });

    it('falls back to the raw action for a value it has no label for', async () => {
      await render(of(makeEntry({ action_type: 'some_future_action' as AuditAction })));

      expect(fields()['פעולה']).toContain('some_future_action');
    });

    it('puts no IP address on screen even if the response carries one', async () => {
      await render(
        of({ ...makeEntry(), ip_address: '203.0.113.7' } as AuditLogEntry & { ip_address: string }),
      );

      expect(text()).not.toContain('203.0.113.7');
      expect(root().innerHTML).not.toContain('203.0.113.7');
    });
  });

  // ---------------------------------------------------------------------------
  // details — readable, not an escaped string
  // ---------------------------------------------------------------------------

  describe('details', () => {
    it('lays the object out as indented JSON', () => {
      expect(details()!.textContent).toBe(JSON.stringify(DETAILS, null, 2));
    });

    it('puts each key on a line of its own, indented by its depth', () => {
      const lines = details()!.textContent!.split('\n');

      expect(lines.length).toBeGreaterThan(10);
      expect(lines).toContain('  "hours": 48,');
      expect(lines).toContain('      "from": "First session",');
    });

    /** What the DoD rules out: JSON printed as a string, quotes escaped. */
    it('is not an escaped string', () => {
      const shown = details()!.textContent!;

      expect(shown).not.toContain('\\"');
      expect(shown.startsWith('"')).toBe(false);
      expect(shown.startsWith('{')).toBe(true);
    });

    it('keeps the values their type — numbers, booleans and null unquoted', () => {
      const shown = details()!.textContent!;

      expect(shown).toContain('"hours": 48');
      expect(shown).toContain('"automatic": false');
      expect(shown).toContain('"reason": null');
    });

    it('shows Hebrew inside details as Hebrew, not as \\u escapes', async () => {
      await render(of(makeEntry({ details: { title: 'מפגש ראשון' } })));

      expect(details()!.textContent).toContain('"title": "מפגש ראשון"');
      expect(details()!.textContent).not.toContain('\\u05');
    });

    /** JSON runs left to right; in an RTL page its punctuation would be reordered. */
    it('sets the JSON left to right, whatever the page direction', () => {
      expect(details()!.getAttribute('dir')).toBe('ltr');
    });

    it('can be reached by keyboard, so a long block can be scrolled', () => {
      expect(details()!.getAttribute('tabindex')).toBe('0');
    });

    it('says so when the entry carries no details', async () => {
      await render(of(makeEntry({ details: null })));

      expect(details()).toBeNull();
      expect(text()).toContain('לרשומה זו לא נשמרו פרטים נוספים.');
    });

    /** `{}` in a code block reads as a rendering fault, not as "nothing recorded". */
    it('treats an empty object as no details', async () => {
      await render(of(makeEntry({ details: {} })));

      expect(details()).toBeNull();
      expect(text()).toContain('לרשומה זו לא נשמרו פרטים נוספים.');
    });
  });

  // ---------------------------------------------------------------------------
  // A modal, not just something that looks like one
  // ---------------------------------------------------------------------------

  describe('as a modal', () => {
    it('is a dialog, modal, named by its own heading', () => {
      const heading = root().querySelector(`#${dialog().getAttribute('aria-labelledby')}`);

      expect(dialog().getAttribute('aria-modal')).toBe('true');
      expect(heading!.textContent!.trim()).toBe('פרטי רשומה');
    });

    it('moves focus into itself when it opens', () => {
      expect(document.activeElement).toBe(closeButton());
    });

    it('closes from its close button', () => {
      closeButton().click();

      expect(closes()).toBe(1);
    });

    it('closes on Escape', () => {
      const event = press('Escape');

      expect(closes()).toBe(1);
      expect(event.defaultPrevented).toBe(true);
    });

    it('closes on a click on the backdrop', () => {
      backdrop().click();

      expect(closes()).toBe(1);
    });

    /** Selecting text in `details` must not throw away the record being read. */
    it('stays open on a click inside the panel', () => {
      details()!.click();
      dialog().click();

      expect(closes()).toBe(0);
    });

    it('wraps Tab from the last control back to the first', () => {
      details()!.focus();

      const event = press('Tab');

      expect(event.defaultPrevented).toBe(true);
      expect(document.activeElement).toBe(closeButton());
    });

    it('wraps Shift+Tab from the first control round to the last', () => {
      closeButton().focus();

      const event = press('Tab', { shiftKey: true });

      expect(event.defaultPrevented).toBe(true);
      expect(document.activeElement).toBe(details());
    });

    it('leaves Tab between two inner controls to the browser', () => {
      closeButton().focus();

      const event = press('Tab');

      expect(event.defaultPrevented).toBe(false);
    });

    it('ignores other keys', () => {
      press('Enter');

      expect(closes()).toBe(0);
    });
  });

  // ---------------------------------------------------------------------------
  // Loading and failing
  // ---------------------------------------------------------------------------

  describe('the states it can be in', () => {
    it('shows a spinner, and the way out, while the entry is in flight', async () => {
      await render(NEVER);

      expect(root().querySelector('app-loading-spinner')).not.toBeNull();
      expect(root().querySelector('dl')).toBeNull();
      expect(document.activeElement).toBe(closeButton());
    });

    it('shows our own message when the request fails without one', async () => {
      await render(throwError(() => ({ status: 500 })));

      expect(root().querySelector('app-error-display')).not.toBeNull();
      expect(text()).toContain('אירעה שגיאה בטעינת הרשומה. נסה שוב.');
      expect(root().querySelector('dl')).toBeNull();
    });

    /** A 404 from the API is a finished sentence, shown as it came. */
    it('shows the API sentence when the response carried one', async () => {
      await render(
        throwError(() => ({
          status: 404,
          error: { detail: 'The audit log entry was not found.' },
        })),
      );

      expect(text()).toContain('The audit log entry was not found.');
    });

    it('tries again, and shows the entry once it arrives', async () => {
      await render(throwError(() => ({ status: 500 })));
      adminServiceMock.getAuditLogEntry.mockReturnValue(of(makeEntry()));

      buttonWith('נסה שוב')!.click();
      fixture.detectChanges();

      expect(adminServiceMock.getAuditLogEntry).toHaveBeenCalledTimes(2);
      expect(root().querySelector('app-error-display')).toBeNull();
      expect(fields()['מזהה רשומה']).toBe('entry-0042');
    });

    it('can still be closed after a failure', async () => {
      await render(throwError(() => ({ status: 500 })));

      press('Escape');

      expect(closes()).toBe(1);
    });

    /** Closed mid-request: the answer has nowhere to land, so it is not awaited. */
    it('lets go of a request still in flight when it is closed', async () => {
      const pending = new Subject<AuditLogEntry>();
      await render(pending);
      expect(pending.observed).toBe(true);

      fixture.destroy();

      expect(pending.observed).toBe(false);
    });
  });

  // ---------------------------------------------------------------------------
  // i18n
  // ---------------------------------------------------------------------------

  describe('i18n', () => {
    it('leaves no Hebrew in the dialog in English', () => {
      switchToEnglish();

      expect(dialog().querySelector('h2')!.textContent!.trim()).toBe('Entry details');
      expect(text()).not.toMatch(HEBREW);
    });

    it('labels every field in English', () => {
      switchToEnglish();

      expect(Object.keys(fields())).toEqual([
        'Action',
        'When',
        'Actor ID',
        'Entity type',
        'Entity ID',
        'Entry ID',
      ]);
      expect(fields()['Action']).toBe('User suspended user_suspended');
    });

    it('leaves no Hebrew on a failed or empty dialog in English', async () => {
      await render(throwError(() => ({ status: 500 })));
      switchToEnglish();
      expect(text()).not.toMatch(HEBREW);

      await render(of(makeEntry({ details: null })));
      switchToEnglish();
      expect(text()).not.toMatch(HEBREW);
    });

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

    it('leaves the identifiers alone, left to right, in both languages', () => {
      const ids = () =>
        [...root().querySelectorAll<HTMLElement>('.entry-dialog__id')].map((dd) => [
          dd.textContent!.trim(),
          dd.getAttribute('dir'),
        ]);
      const expected = [
        ['admin-0001', 'ltr'],
        ['User', 'ltr'],
        ['user-0009', 'ltr'],
        ['entry-0042', 'ltr'],
      ];

      expect(ids()).toEqual(expected);
      switchToEnglish();
      expect(ids()).toEqual(expected);
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      expect(backdrop().hasAttribute('dir')).toBe(false);
      expect(dialog().hasAttribute('dir')).toBe(false);
    });
  });
});
