/**
 * The moderator reports screen had no spec before ABF-134.
 *
 * It is a screen made almost entirely of copy — a heading, an empty state and
 * four labelled fields per card — so the migration is exactly what needs a
 * guard: without one, nothing catches a label falling back to hardcoded
 * Hebrew, or a raw `moderator.reports.title` reaching the page. The behaviour
 * the screen already had (load, spinner, failure, preview) is pinned here too,
 * for the same reason ABF-132 pinned the dashboard's: a spec that only knows
 * about text lets the next change break the list silently.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, Observable, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ModeratorReportsComponent } from './reports.component';
import {
  PostStatus,
  ReportDecision,
  ReportReason,
  ReportTargetType,
} from '../../../core/constants';
import type { ReportList, ReportWithContent } from '../../../core/models';
import { ReportService } from '../../../core/services/report.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

function makeReport(overrides: Partial<ReportWithContent> = {}): ReportWithContent {
  return {
    id: 'r1',
    reporter_id: 'u1',
    reported_user_id: 'u2',
    target_type: ReportTargetType.FORUM_POST,
    target_id: 'p1',
    reason: ReportReason.HARASSMENT,
    description: 'הכותב/ת מקלל/ת',
    decision: ReportDecision.PENDING,
    moderator_id: null,
    moderator_note: null,
    decided_at: null,
    created_at: '2026-07-01T10:00:00',
    content_title: 'כותרת הפוסט',
    content_text: 'גוף הפוסט',
    content_status: PostStatus.VISIBLE,
    report_count: 3,
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

function makeList(overrides: Partial<ReportList> = {}): ReportList {
  return { items: [makeReport()], total: 1, pending_count: 1, ...overrides };
}

describe('ModeratorReportsComponent', () => {
  let fixture: ComponentFixture<ModeratorReportsComponent>;
  let component: ModeratorReportsComponent;

  /** Builds the screen against one service response. */
  async function renderWith(pendingReports: Observable<ReportList>): Promise<void> {
    TestBed.resetTestingModule();

    await TestBed.configureTestingModule({
      imports: [ModeratorReportsComponent, translocoTesting()],
      providers: [
        {
          provide: ReportService,
          useValue: { getPendingReports: vi.fn().mockReturnValue(pendingReports) },
        },
      ],
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

  /** One card per report — reached from its title, the only anchor it has. */
  function cards(): HTMLElement[] {
    return [...root().querySelectorAll('h3')].map(
      (title) => title.parentElement!.parentElement as HTMLElement,
    );
  }

  /** The card's four `<p>` rows: preview, reason, description, content status. */
  function fieldsOf(card: HTMLElement): string[] {
    return [...card.querySelectorAll('p')].map((row) =>
      row.textContent!.replace(/\s+/g, ' ').trim(),
    );
  }

  function badges(): string[] {
    return [...root().querySelectorAll('h3 + span')].map((badge) => badge.textContent!.trim());
  }

  function buttonLabels(): string[] {
    return [...root().querySelectorAll('button')].map((button) => button.textContent!.trim());
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  describe('loading the pending reports', () => {
    it('lists what the service returns', async () => {
      await renderWith(of(makeList({ items: [makeReport(), makeReport({ id: 'r2' })] })));

      expect(component.isLoading()).toBe(false);
      expect(component.hasError()).toBe(false);
      expect(component.pendingReports().length).toBe(2);
      expect(cards().length).toBe(2);
    });

    it('shows a spinner instead of the list while the request is in flight', async () => {
      await renderWith(NEVER);

      expect(component.isLoading()).toBe(true);
      expect(root().querySelector('app-loading-spinner')).toBeTruthy();
      expect(cards()).toEqual([]);
    });

    it('shows a failure and no empty state when the request fails', async () => {
      await renderWith(throwError(() => ({})));

      expect(component.hasError()).toBe(true);
      expect(component.isLoading()).toBe(false);
      expect(root().querySelector('app-error-display')).toBeTruthy();
      expect(text()).not.toContain('אין דיווחים ממתינים');
    });

    it('says so when there is nothing waiting', async () => {
      await renderWith(of(makeList({ items: [], total: 0, pending_count: 0 })));

      expect(cards()).toEqual([]);
      expect(text()).toContain('אין דיווחים ממתינים. כל הכבוד!');
    });

    it('cuts a long body down to a preview', async () => {
      await renderWith(of(makeList()));

      expect(component.previewOf('a'.repeat(200))).toBe('a'.repeat(200));
      expect(component.previewOf('a'.repeat(201))).toBe(`${'a'.repeat(200)}…`);
    });
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as it did before the keys went in', async () => {
      await renderWith(of(makeList()));

      expect(heading()).toBe('לוח בקרת מבקר – דיווחים ממתינים');
      expect(badges()).toEqual(['3 דיווחים']);
      expect(fieldsOf(cards()[0])).toEqual([
        'גוף הפוסט',
        'סיבה: הטרדה',
        'תיאור: הכותב/ת מקלל/ת',
        'סטטוס תוכן: גלוי',
      ]);
      expect(buttonLabels()).toEqual(['מחיקת ההודעה (מוצדק)', 'ביטול הדיווח (שגוי)']);
    });

    it('leaves no Hebrew on the page in English', async () => {
      await renderWith(of(makeList({ items: [makeLatinReport()] })));

      switchToEnglish();

      expect(heading()).toBe('Moderator dashboard – pending reports');
      expect(badges()).toEqual(['3 reports']);
      expect(fieldsOf(cards()[0])).toEqual([
        'Body text',
        'Reason: Harassment',
        'Description: The author is swearing',
        'Content status: Visible',
      ]);
      expect(buttonLabels()).toEqual([
        'Delete the message (valid)',
        'Dismiss the report (invalid)',
      ]);
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the empty state in English', async () => {
      await renderWith(of(makeList({ items: [], total: 0, pending_count: 0 })));

      switchToEnglish();

      expect(text()).toContain('No pending reports. Nice work!');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the page while the list is still loading', async () => {
      await renderWith(NEVER);
      expect(text()).toContain('טוען דיווחים...');

      switchToEnglish();

      expect(root().querySelector('app-loading-spinner')).toBeTruthy();
      expect(text()).toContain('Loading reports...');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders the failure copy in the new language', async () => {
      await renderWith(throwError(() => ({})));
      expect(text()).toContain('שגיאה בטעינת הדיווחים.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong loading the reports.');
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The reason and the content status are two of the ten shared label maps
     * (ABF-127). This module renders them through the pipe and adds no key of
     * its own for them — the rename below is what a private copy would hide.
     */
    it('takes the reason and the status from the shared constants, not its own keys', async () => {
      await renderWith(of(makeList()));
      const transloco = TestBed.inject(TranslocoService);

      transloco.setTranslationKey('constants.report_reason.harassment', 'מילה אחרת', {
        lang: 'he',
      });
      transloco.setTranslationKey('constants.post_status.visible', 'מצב אחר', { lang: 'he' });
      fixture.detectChanges();

      expect(fieldsOf(cards()[0])).toContain('סיבה: מילה אחרת');
      expect(fieldsOf(cards()[0])).toContain('סטטוס תוכן: מצב אחר');
    });

    /**
     * "3 דיווחים" and "3 reports" happen to put the number in the same place,
     * but a wording that did not would need it to move inside the sentence —
     * which two separate text nodes cannot do (ABF-131).
     */
    it('builds the counter from one key with the count as a parameter', async () => {
      await renderWith(of(makeList({ items: [makeReport({ report_count: 12 })] })));
      const transloco = TestBed.inject(TranslocoService);

      transloco.setTranslationKey('moderator.reports.report_count', 'סך הכול {{count}}', {
        lang: 'he',
      });
      fixture.detectChanges();

      expect(badges()).toEqual(['סך הכול 12']);
    });

    /**
     * The reported post and the reporter's own words are user content: they
     * stay in the language they were written in, in either UI language
     * (ABF-130).
     */
    it('leaves the reported content in the language it was written in', async () => {
      await renderWith(of(makeList()));

      switchToEnglish();

      expect(cards()[0].querySelector('h3')!.textContent!.trim()).toBe('כותרת הפוסט');
      expect(fieldsOf(cards()[0])).toContain('גוף הפוסט');
      expect(fieldsOf(cards()[0])).toContain('Description: הכותב/ת מקלל/ת');
    });

    /**
     * A dash is a glyph, not copy — it reads the same in both languages and is
     * Bidi-neutral, so it stays out of the translation files. Same call the
     * dashboard chevron got in ABF-132.
     */
    it('keeps the empty-description dash as a glyph in either language', async () => {
      await renderWith(of(makeList({ items: [makeLatinReport({ description: null })] })));
      expect(fieldsOf(cards()[0])).toContain('תיאור: –');

      switchToEnglish();

      expect(fieldsOf(cards()[0])).toContain('Description: –');
      expect(text()).not.toMatch(HEBREW);
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await renderWith(of(makeList()));
      const page = root().querySelector('div') as HTMLElement;

      expect(root().hasAttribute('dir')).toBe(false);
      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });

    /**
     * The gap between the two decision buttons was a hardcoded `margin-right`,
     * which is the gap only while the page runs RTL; in English it jumped to
     * the outside of the pair. A logical property is the same 0.5rem in Hebrew
     * and the correct side in English.
     */
    it('spaces the decision buttons on the logical side, not the right', async () => {
      await renderWith(of(makeList()));
      const dismiss = root().querySelectorAll('button')[1] as HTMLElement;

      expect(dismiss.style.marginInlineStart).toBe('0.5rem');
      expect(dismiss.style.marginRight).toBe('');
    });

    /**
     * A <button> with no type is type="submit". Neither decision button submits
     * anything, and the moment either one lands inside a <form> — a note field
     * is the next step on this screen — the default would submit it instead of
     * running the click handler. CONTRIBUTING §5 asks for type="button" always.
     */
    it('gives both decision buttons an explicit type="button"', async () => {
      await renderWith(of(makeList()));
      const buttons = [...root().querySelectorAll('button')];

      expect(buttons.length).toBe(2);
      expect(buttons.map((button) => button.getAttribute('type'))).toEqual(['button', 'button']);
    });
  });
});
