/**
 * One report on a screen of its own: what the moderator is shown before she
 * decides, and what she is shown after.
 *
 * Three things here are not repeats of the queue's spec, and are why this file
 * is as long as it is:
 *
 *   - the content arrives **whole**. The queue cuts every post at 200
 *     characters, and a detail screen that inherited that would be a second
 *     copy of the queue with a back link.
 *   - the reporter is never named. The API sends an opaque id; the assertion
 *     that it does not reach the page is the only thing standing between §7.1
 *     and a uuid rendered in a `<dd>`.
 *   - the member's card is a **second** request, and its failure is not the
 *     report's. A card that never arrives has to cost this screen a name and
 *     three counts and nothing else.
 *
 * The `i18n` block is the guard CONTRIBUTING §6 asks of a screen added to a
 * module that has already been migrated, including the two things the text
 * sweep cannot see: the `aria-label`s, and the labels this screen renders out
 * of the two neighbouring namespaces rather than out of private copies.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ModeratorReportDetailComponent } from './report-detail.component';
import { ReportService } from '../../../core/services/report.service';
import {
  AccountStatus,
  PostStatus,
  ReportDecision,
  ReportReason,
  ReportTargetType,
  Sector,
  UserType,
} from '../../../core/constants';
import type {
  DirectMessageReport,
  ForumPostReport,
  UserModerationCard,
} from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

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
 * The same report with no Hebrew in anything a member wrote.
 *
 * The post's title, its body and the words the reporter typed are user content
 * — never translated (ABF-130) — so they would fail the `HEBREW` sweeps below
 * for the one reason those sweeps are not meant to catch.
 */
function makeLatinReport(overrides: Partial<ForumPostReport> = {}): ForumPostReport {
  return makeReport({
    content_title: 'A post about the paperwork',
    content_text: 'Body text',
    description: 'The author is swearing',
    ...overrides,
  });
}

/** A report that has already been decided, as the screen reads it back. */
const DECIDED = {
  decision: ReportDecision.VALID,
  moderator_id: 'mod-1',
  decided_at: '2026-07-16T10:00:00',
  content_status: PostStatus.DELETED,
};

/**
 * A report about a private message (ABF-113).
 *
 * It carries no title, no post status and no report count — nothing about a
 * forum post exists on it — and `message_content` is the decrypted text that
 * only `getReport()` ever returns, on the call this screen makes to draw
 * itself.
 */
function makeDmReport(overrides: Partial<DirectMessageReport> = {}): DirectMessageReport {
  return {
    id: 'report-1',
    reporter_id: 'user-1',
    reported_user_id: 'user-2',
    target_type: ReportTargetType.DIRECT_MESSAGE,
    target_id: 'msg-1',
    reason: ReportReason.HARASSMENT,
    description: 'התבטאות פוגענית',
    decision: ReportDecision.PENDING,
    moderator_id: null,
    moderator_note: null,
    decided_at: null,
    created_at: '2026-07-15T09:30:00',
    message_content: 'תוכן ההודעה הפרטית',
    ...overrides,
  };
}

function makeCard(overrides: Partial<UserModerationCard> = {}): UserModerationCard {
  return {
    id: 'user-2',
    first_name: 'רחל',
    last_name: 'כהן',
    user_type: UserType.WIDOW,
    sector: Sector.HASIDIC,
    account_status: AccountStatus.ACTIVE,
    reports_against_total: 4,
    reports_against_valid: 3,
    reports_against_invalid: 1,
    reports_filed_total: 2,
    false_reports_filed: 1,
    is_suspended: false,
    suspended_until: null,
    ...overrides,
  };
}

/** The same card for a member whose name carries no Hebrew — see above. */
function makeLatinCard(): UserModerationCard {
  return makeCard({ first_name: 'Rachel', last_name: 'Cohen' });
}

describe('ModeratorReportDetailComponent', () => {
  let fixture: ComponentFixture<ModeratorReportDetailComponent>;
  let component: ModeratorReportDetailComponent;
  let reportServiceMock: {
    getReport: ReturnType<typeof vi.fn>;
    getUserCard: ReturnType<typeof vi.fn>;
    decideReport: ReturnType<typeof vi.fn>;
  };

  /** Builds the screen with the :id route parameter already bound. */
  async function render({
    report = of(makeReport()),
    card = of(makeCard()),
    id = 'report-1',
  }: { report?: unknown; card?: unknown; id?: string } = {}): Promise<void> {
    TestBed.resetTestingModule();

    reportServiceMock = {
      getReport: vi.fn().mockReturnValue(report),
      getUserCard: vi.fn().mockReturnValue(card),
      decideReport: vi.fn().mockReturnValue(of(makeReport(DECIDED))),
    };

    await TestBed.configureTestingModule({
      imports: [ModeratorReportDetailComponent, translocoTesting()],
      providers: [{ provide: ReportService, useValue: reportServiceMock }, provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(ModeratorReportDetailComponent);
    fixture.componentRef.setInput('id', id);
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

  /** Every `<dt>: <dd>` row on the page, whitespace collapsed. */
  function fields(): string[] {
    return [...root().querySelectorAll('.report__meta > div')].map((row) => {
      const term = row.querySelector('dt')!.textContent!.replace(/\s+/g, ' ').trim();
      const value = row.querySelector('dd')!.textContent!.replace(/\s+/g, ' ').trim();
      return `${term}: ${value}`;
    });
  }

  function sectionHeadings(): string[] {
    return [...root().querySelectorAll('.report__section')].map((h) => h.textContent!.trim());
  }

  function statLabels(): string[] {
    return [...root().querySelectorAll('.stats dt')].map((term) => term.textContent!.trim());
  }

  function statCounts(): string[] {
    return [...root().querySelectorAll('.stats dd')].map((count) => count.textContent!.trim());
  }

  function decideButtons(): HTMLButtonElement[] {
    return [...root().querySelectorAll<HTMLButtonElement>('.report__actions .btn')];
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

  describe('the report', () => {
    it('loads the report named in the route', () => {
      expect(reportServiceMock.getReport).toHaveBeenCalledWith('report-1');
      expect(component.isLoading()).toBe(false);
      expect(component.hasError()).toBe(false);
    });

    /**
     * The queue cuts every post at 200 characters so a moderator can scan the
     * list. This screen is where the rest of it is, and a preview here would
     * make the whole page a second copy of the row it was opened from.
     */
    it('shows the reported content whole, not the queue preview of it', async () => {
      const long = 'א'.repeat(250);
      await render({ report: of(makeReport({ content_text: long })) });

      const content = root().querySelector('.report__content')!.textContent!;
      expect(content).toBe(long);
      expect(content).not.toContain('…');
    });

    it('shows what the decision rests on', () => {
      expect(text()).toContain('כותרת ההודעה');
      expect(text()).toContain('תוכן ההודעה שדווחה');
      expect(text()).toContain('הטרדה');
      expect(text()).toContain('התבטאות פוגענית');
      expect(text()).toContain('15/07/2026 09:30');
      expect(text()).toContain('גלוי');
    });

    /**
     * §7.1's protection of the reporter, and the reason the API sends an
     * opaque id rather than a name. The count is what the moderator is given
     * instead, and it is on the page beside this.
     */
    it('never names the reporter, and does not fall back to showing the id', () => {
      expect(text()).not.toContain('user-1');
      expect(text()).toContain('הזהות אינה מוצגת כאן');
      expect(text()).toContain('2');
    });

    /**
     * §9.4 keeps a report for five years without the person behind it, so a
     * null reporter is a closed account rather than a report that arrived with
     * nobody behind it — and the two read differently to a moderator.
     */
    it('says so when the reporter has since closed her account', async () => {
      await render({ report: of(makeReport({ reporter_id: null })) });

      expect(component.reporterKey()).toBe('moderator.report_detail.reporter_anonymized');
      expect(text()).toContain('החשבון שממנו הוגש הדיווח נסגר');
    });

    it('falls back to a dash for a report the reporter left no words in', async () => {
      await render({ report: of(makeReport({ description: null })) });

      expect(fields()).toContain('פירוט המדווח/ת: –');
    });

    it('opens the way through to the reported member’s card', () => {
      const link: HTMLAnchorElement = root().querySelector('.report__card-link')!;

      expect(link.getAttribute('href')).toBe('/moderator/users/user-2');
      expect(link.getAttribute('aria-label')).toContain('כותרת ההודעה');
    });

    it('names the reported member once her card has arrived', () => {
      expect(component.reportedUserName()).toBe('רחל כהן');
      expect(text()).toContain('רחל כהן');
    });

    it('shows a spinner instead of the report while the request is in flight', async () => {
      await render({ report: NEVER });

      expect(component.isLoading()).toBe(true);
      expect(root().querySelector('app-loading-spinner')).toBeTruthy();
      expect(root().querySelector('.report')).toBeNull();
    });

    it('sets hasError when the report fails to load', async () => {
      await render({ report: throwError(() => ({})) });

      expect(component.hasError()).toBe(true);
      expect(component.isLoading()).toBe(false);
      expect(text()).toContain('אירעה שגיאה בטעינת הדיווח');
      expect(root().querySelector('.report')).toBeNull();
    });
  });

  /**
   * ABF-113 landed while this screen was being built, and it changed what a
   * report can be: a report about a private message carries no title, no post
   * status and no report count, and its plaintext exists only on the call this
   * screen makes to draw itself. These pin the branch, and the sentence that
   * tells the moderator her read was recorded.
   */
  describe('a report about a private message', () => {
    it('shows the decrypted message this screen’s own load returned', async () => {
      await render({ report: of(makeDmReport()) });

      expect(component.isDirectMessage()).toBe(true);
      expect(root().querySelector('.report__content')!.textContent!.trim()).toBe(
        'תוכן ההודעה הפרטית',
      );
    });

    /** No post exists, so neither row has anything true to say. */
    it('drops the rows that only a forum post has', async () => {
      await render({ report: of(makeDmReport()) });

      const terms = fields().map((row) => row.split(':')[0]);
      expect(terms).not.toContain('מצב ההודעה');
      expect(terms).not.toContain('מספר הדיווחים על התוכן');
      expect(terms).toContain('סיבת הדיווח');
    });

    it('takes a generic title, since a private message has none', async () => {
      await render({ report: of(makeDmReport()) });

      expect(component.reportTitle()).toBe('הודעה פרטית');
    });

    /**
     * The queue asks before it decrypts, because a row does not need the
     * plaintext. This screen cannot — the same call is where its reason, its
     * dates and its decision came from — so the read has already happened by
     * the time the page is drawn, and §9.3 says the moderator should know.
     */
    it('says out loud that the read was recorded in the audit log', async () => {
      await render({ report: of(makeDmReport()) });

      expect(text()).toContain('נרשמה ביומן הביקורת');
    });

    it('says nothing of the kind for a forum post, which is not decrypted', () => {
      expect(component.isDirectMessage()).toBe(false);
      expect(root().querySelector('.report__audited')).toBeNull();
    });

    /**
     * §9.4: the reported-on account is gone and the message went with it. The
     * report is kept, and there is no content to show even to the moderator
     * who would have ruled on it.
     */
    it('explains a report closed because the account was deleted', async () => {
      await render({
        report: of(
          makeDmReport({
            decision: ReportDecision.CLOSED_ACCOUNT_DELETED,
            message_content: null,
          }),
        ),
      });

      expect(text()).toContain('הדיווח נסגר עקב מחיקת חשבון');
      expect(text()).not.toContain('תוכן ההודעה הפרטית');
      expect(decideButtons()).toEqual([]);
    });
  });

  describe('the decisions already taken about the member', () => {
    it('loads the card of the member the report names', () => {
      expect(reportServiceMock.getUserCard).toHaveBeenCalledWith('user-2');
      expect(component.isCardLoading()).toBe(false);
      expect(component.cardError()).toBe(false);
    });

    it('shows the counts the earlier decisions come to', () => {
      expect(statCounts()).toEqual(['4', '3', '1']);
    });

    /** There is no member to ask about until the report says who it is. */
    it('asks for no card when the report never arrived', async () => {
      await render({ report: throwError(() => ({})) });

      expect(reportServiceMock.getUserCard).not.toHaveBeenCalled();
    });

    /**
     * The card is a second request, and the report does not depend on it. A
     * screen that blanked itself because the history failed would take a
     * decidable report away over three numbers.
     */
    it('leaves the report readable and decidable when the card fails', async () => {
      await render({ card: throwError(() => ({})) });

      expect(component.cardError()).toBe(true);
      expect(component.hasError()).toBe(false);
      expect(text()).toContain('לא ניתן לטעון כעת את היסטוריית ההחלטות');
      expect(text()).toContain('תוכן ההודעה שדווחה');
      expect(decideButtons()).toHaveLength(2);
      expect(root().querySelector('.stats')).toBeNull();
    });

    it('marks the section busy rather than empty while the card is in flight', async () => {
      await render({ card: NEVER });

      const region = root().querySelector('[aria-live="polite"]')!;
      expect(region.getAttribute('aria-busy')).toBe('true');
      expect(region.querySelector('app-loading-spinner')).toBeTruthy();
      expect(text()).not.toContain('לא ניתן לטעון');
    });
  });

  describe('deciding on the report', () => {
    it('offers the two buttons while the report is still waiting', () => {
      expect(component.isPending()).toBe(true);
      expect(decideButtons().map((button) => button.textContent!.trim())).toEqual([
        'מחיקת ההודעה (מוצדק)',
        'ביטול הדיווח (שגוי)',
      ]);
    });

    /**
     * The server answers 409 to a second decision on the same report, so the
     * screen that reads a decided one back does not offer a button that was
     * going to be refused.
     */
    it('reads the decision back instead, once one has been taken', async () => {
      await render({
        report: of(makeReport({ ...DECIDED, moderator_note: 'תוכן פוגעני' })),
      });

      expect(component.isPending()).toBe(false);
      expect(decideButtons()).toEqual([]);
      expect(text()).toContain('הדיווח התקבל');
      expect(text()).toContain('תוכן פוגעני');
      expect(text()).toContain('16/07/2026 10:00');
      expect(text()).toContain('מחוק');
    });

    it('falls back to a dash for a decision taken before notes were required', async () => {
      await render({ report: of(makeReport({ ...DECIDED, moderator_note: null })) });

      expect(fields()).toContain('הערת המבקר/ת: –');
    });

    it('does not call the service until the decision is confirmed', () => {
      component.decide(ReportDecision.VALID);
      fixture.detectChanges();

      expect(reportServiceMock.decideReport).not.toHaveBeenCalled();
      expect(root().querySelector('app-confirm-dialog')).toBeTruthy();
    });

    it('sends the decision with the note the moderator wrote', () => {
      component.decide(ReportDecision.VALID);

      component.confirmDecision('תוכן פוגעני');

      expect(reportServiceMock.decideReport).toHaveBeenCalledWith('report-1', {
        decision: ReportDecision.VALID,
        note: 'תוכן פוגעני',
      });
    });

    /**
     * The reply carries the report's own fields and not the post's, and a
     * decision rewrites both — so the screen asks the server what it now holds
     * rather than deriving the post's new status from the decision it sent.
     */
    it('loads the report and the card again after a decision', () => {
      component.decide(ReportDecision.VALID);

      component.confirmDecision('תוכן פוגעני');
      fixture.detectChanges();

      expect(reportServiceMock.getReport).toHaveBeenCalledTimes(2);
      expect(reportServiceMock.getUserCard).toHaveBeenCalledTimes(2);
      expect(component.pendingDecision()).toBeNull();
    });

    it('closes the dialog without deciding on cancel', () => {
      component.decide(ReportDecision.VALID);

      component.cancelDecision();
      fixture.detectChanges();

      expect(component.pendingDecision()).toBeNull();
      expect(reportServiceMock.decideReport).not.toHaveBeenCalled();
      expect(root().querySelector('app-confirm-dialog')).toBeNull();
    });

    it('shows the backend message when the decision is refused', () => {
      reportServiceMock.decideReport.mockReturnValue(
        throwError(() => ({ error: { detail: 'הדיווח כבר טופל.' } })),
      );
      component.decide(ReportDecision.VALID);

      component.confirmDecision('תוכן פוגעני');
      fixture.detectChanges();

      expect(component.actionError()).toEqual({ key: '', text: 'הדיווח כבר טופל.' });
      expect(text()).toContain('הדיווח כבר טופל.');
      expect(reportServiceMock.getReport).toHaveBeenCalledTimes(1);
    });

    it('falls back to a key of ours when the failure carries no detail', () => {
      reportServiceMock.decideReport.mockReturnValue(throwError(() => ({ error: null })));
      component.decide(ReportDecision.VALID);

      component.confirmDecision('תוכן פוגעני');
      fixture.detectChanges();

      expect(component.actionError()).toEqual({ key: 'moderator.errors.decide_failed', text: '' });
      expect(text()).toContain('אירעה שגיאה בשמירת ההחלטה. נסי שוב.');
    });

    it('confirms with the sentence that matches the button pressed', () => {
      component.decide(ReportDecision.VALID);
      fixture.detectChanges();
      const dialog = (): HTMLElement => root().querySelector('app-confirm-dialog')!;
      expect(dialog().textContent).toContain('תוסר מהפורום');

      component.decide(ReportDecision.INVALID);
      fixture.detectChanges();

      expect(dialog().textContent).toContain('תוצג שוב');
    });
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as the screen was written', () => {
      expect(heading()).toBe('פרטי דיווח');
      // '‹' is Bidi_Mirrored, so it turns with <html dir> on its own and stays
      // in the markup — direction.spec.ts holds the whole app to that.
      expect(root().querySelector('.page__back')!.textContent!.replace(/\s+/g, ' ').trim()).toBe(
        '‹ חזרה ללוח הבקרה',
      );
      expect(sectionHeadings()).toEqual([
        'התוכן המדווח',
        'פרטי הדיווח',
        'החלטה',
        'היסטוריית החלטות קודמות',
      ]);
      expect(fields()).toEqual([
        'סיבת הדיווח: הטרדה',
        'תאריך הדיווח: 15/07/2026 09:30',
        'מצב ההודעה: גלוי',
        'מספר הדיווחים על התוכן: 2',
        'פירוט המדווח/ת: התבטאות פוגענית',
        'מגיש/ת הדיווח: הזהות אינה מוצגת כאן. ההחלטה מתקבלת לפי התוכן ולפי מה שנכתב בדיווח.',
        'המשתמש/ת שדווח/ה: רחל כהן כרטיס המשתמש/ת',
      ]);
      expect(statLabels()).toEqual([
        'דיווחים נגד המשתמש/ת',
        'מהם נמצאו מוצדקים',
        'מהם נמצאו שגויים',
      ]);
    });

    it('leaves no Hebrew on the page in English', async () => {
      await render({ report: of(makeLatinReport()), card: of(makeLatinCard()) });

      switchToEnglish();

      expect(heading()).toBe('Report details');
      expect(sectionHeadings()).toEqual([
        'The reported content',
        'About the report',
        'Decision',
        'Previous decisions',
      ]);
      expect(fields()).toEqual([
        'Report reason: Harassment',
        'Report date: 15/07/2026 09:30',
        'Message status: Visible',
        'Reports on this content: 2',
        'What the reporter wrote: The author is swearing',
        'Who filed the report: Not named here. The decision rests on the content and on what the report says.',
        'The reported member: Rachel Cohen User card',
      ]);
      expect(statLabels()).toEqual([
        'Reports against this user',
        'Of those, found valid',
        'Of those, found invalid',
      ]);
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on a report that has already been decided', async () => {
      await render({
        report: of(makeLatinReport({ ...DECIDED, moderator_note: 'Offensive content' })),
        card: of(makeLatinCard()),
      });
      expect(text()).toContain('הדיווח התקבל');

      switchToEnglish();

      expect(sectionHeadings()).toContain('The decision taken');
      expect(text()).toContain('Report upheld');
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The sweep above reads `textContent`, which an `aria-label` is not part
     * of — a screen reader would have gone on reading Hebrew on an English
     * page and nothing would have said so. All three name the reported post,
     * so they are also the parameters check.
     */
    it('translates the aria-labels, which the text sweep cannot see', async () => {
      await render({ report: of(makeLatinReport()), card: of(makeLatinCard()) });

      expect(ariaLabels()).toEqual([
        'כרטיס המשתמש/ת שכתב/ה את ״A post about the paperwork״',
        'מחיקת ההודעה ״A post about the paperwork״',
        'ביטול הדיווח על ״A post about the paperwork״',
      ]);

      switchToEnglish();

      expect(ariaLabels()).toEqual([
        'Card of the user who wrote “A post about the paperwork”',
        'Delete the message “A post about the paperwork”',
        'Dismiss the report about “A post about the paperwork”',
      ]);
      expect(ariaLabels().join(' ')).not.toMatch(HEBREW);
    });

    /**
     * The reason, the message status and the decision come out of the shared
     * label maps (ABF-127) with no key of this module's own. The rename is
     * what a private copy would hide: it would go on saying "הטרדה" while the
     * platform's own vocabulary had moved.
     */
    it('takes the reason and the status from the shared constants', () => {
      const transloco = TestBed.inject(TranslocoService);
      transloco.setTranslationKey('constants.report_reason.harassment', 'סיבה אחרת', {
        lang: 'he',
      });
      transloco.setTranslationKey('constants.post_status.visible', 'מצב אחר', { lang: 'he' });
      fixture.detectChanges();

      expect(fields()).toContain('סיבת הדיווח: סיבה אחרת');
      expect(fields()).toContain('מצב ההודעה: מצב אחר');
    });

    /**
     * The field labels are the queue's and the counts are the user card's —
     * this screen renders another screen's payload, so it renders that
     * payload's labels rather than a private copy that could drift from them
     * (CONTRIBUTING §6).
     */
    it('renders the report and the card through the keys those screens own', () => {
      const transloco = TestBed.inject(TranslocoService);
      transloco.setTranslationKey('moderator.reports.reason_label', 'למה דווח', { lang: 'he' });
      transloco.setTranslationKey('moderator.user_card.reports_against_total', 'סה״כ', {
        lang: 'he',
      });
      fixture.detectChanges();

      expect(fields()).toContain('למה דווח: הטרדה');
      expect(statLabels()).toContain('סה״כ');
    });

    /** The dialog is shared and takes finished text — the caller runs the pipe. */
    it('translates the confirmation through the caller, not the dialog', async () => {
      await render({ report: of(makeLatinReport()), card: of(makeLatinCard()) });
      component.decide(ReportDecision.VALID);
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

    it('re-renders a failure of ours in the new language', async () => {
      await render({ report: of(makeLatinReport()), card: of(makeLatinCard()) });
      reportServiceMock.decideReport.mockReturnValue(throwError(() => ({ error: null })));
      component.decide(ReportDecision.VALID);
      component.confirmDecision('Offensive content');
      fixture.detectChanges();
      expect(text()).toContain('אירעה שגיאה בשמירת ההחלטה. נסי שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong saving the decision.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the failure to load the report, in English', async () => {
      await render({ report: throwError(() => ({})) });
      expect(text()).toContain('אירעה שגיאה בטעינת הדיווח.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong loading the report.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      const page = root().querySelector('.page') as HTMLElement;

      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });
  });
});
