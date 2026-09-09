/**
 * The moderator's user card: the counts a suspension decision rests on, and
 * the suspension itself.
 *
 * The `i18n` block is the guard CONTRIBUTING §6 asks of a screen added to a
 * module that has already been migrated — including the two things the text
 * sweep cannot see on its own: the cell label, which TypeScript assembles out
 * of two shared label keys, and the suspension line, which names the person
 * inside a translated sentence.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ModeratorUserCardComponent } from './user-card.component';
import { ReportService } from '../../../core/services/report.service';
import { AccountStatus, Sector, UserType } from '../../../core/constants';
import type { UserModerationCard } from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

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

/**
 * The same card for a user whose name carries no Hebrew.
 *
 * A person's name is content, never translated (ABF-130), so it would fail the
 * `HEBREW` sweeps below for the one reason they are not meant to catch.
 */
function makeLatinCard(overrides: Partial<UserModerationCard> = {}): UserModerationCard {
  return makeCard({ first_name: 'Rachel', last_name: 'Cohen', ...overrides });
}

const SUSPENDED = {
  account_status: AccountStatus.SUSPENDED,
  is_suspended: true,
  suspended_until: '2026-08-20T12:00:00',
};

describe('ModeratorUserCardComponent', () => {
  let fixture: ComponentFixture<ModeratorUserCardComponent>;
  let component: ModeratorUserCardComponent;
  let reportServiceMock: {
    getUserCard: ReturnType<typeof vi.fn>;
    suspendUser: ReturnType<typeof vi.fn>;
  };

  /** Builds the screen with the :userId route parameter already bound. */
  async function render(card: UserModerationCard = makeCard(), userId = 'user-2'): Promise<void> {
    TestBed.resetTestingModule();

    reportServiceMock = {
      getUserCard: vi.fn().mockReturnValue(of(card)),
      suspendUser: vi.fn().mockReturnValue(of({ ...card, ...SUSPENDED })),
    };

    await TestBed.configureTestingModule({
      imports: [ModeratorUserCardComponent, translocoTesting()],
      providers: [{ provide: ReportService, useValue: reportServiceMock }, provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(ModeratorUserCardComponent);
    fixture.componentRef.setInput('userId', userId);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function root(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return root().textContent ?? '';
  }

  function statLabels(): string[] {
    return [...root().querySelectorAll('.stats dt')].map((term) => term.textContent!.trim());
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await render();
  });

  describe('the card', () => {
    it('loads the card of the user named in the route', () => {
      expect(reportServiceMock.getUserCard).toHaveBeenCalledWith('user-2');
      expect(component.isLoading()).toBe(false);
      expect(component.hasError()).toBe(false);
    });

    it('shows the moderation history the decision rests on', () => {
      expect(text()).toContain('רחל כהן');
      expect(text()).toContain('אלמנה');
      expect(text()).toContain('חסידי');
      expect(text()).toContain('פעיל');
      expect(component.cellLabel()).toBe('אלמנה · חסידי');
    });

    it('shows every count the card is made of', () => {
      const counts = [...root().querySelectorAll<HTMLElement>('.stats dd')].map((dd) =>
        dd.textContent?.trim(),
      );

      expect(counts).toEqual(['4', '3', '1', '2', '1']);
    });

    it('says the account is not suspended when it is not', () => {
      expect(text()).toContain('החשבון אינו מושעה כרגע');
    });

    it('shows until when a suspended account is suspended', async () => {
      await render(makeCard(SUSPENDED));

      expect(text()).toContain('20/08/2026');
      expect(text()).toContain('מושעה');
    });

    it('falls back to a dash for a user placed in no cell yet', async () => {
      await render(makeCard({ user_type: null, sector: null }));

      expect(component.cellLabel()).toBe('—');
    });

    it('sets hasError when the card fails to load', async () => {
      await render();
      reportServiceMock.getUserCard.mockReturnValue(throwError(() => ({})));

      component.ngOnInit();
      fixture.detectChanges();

      expect(component.hasError()).toBe(true);
      expect(component.isLoading()).toBe(false);
      expect(text()).toContain('אירעה שגיאה בטעינת כרטיס המשתמש');
    });
  });

  describe('suspending the user', () => {
    it('does not call the service until the dialog is confirmed', () => {
      component.openSuspendDialog();
      fixture.detectChanges();

      expect(reportServiceMock.suspendUser).not.toHaveBeenCalled();
      expect(root().querySelector('app-suspend-dialog')).toBeTruthy();
    });

    it('sends the duration and the reason the moderator wrote', () => {
      component.openSuspendDialog();

      component.confirmSuspend({ hours: 48, reason: 'התנהגות פוגענית חוזרת' });

      expect(reportServiceMock.suspendUser).toHaveBeenCalledWith(
        'user-2',
        48,
        'התנהגות פוגענית חוזרת',
      );
    });

    it('shows the suspension the moment it is applied, without refetching', () => {
      component.openSuspendDialog();

      component.confirmSuspend({ hours: 48, reason: 'התנהגות פוגענית חוזרת' });
      fixture.detectChanges();

      expect(component.card()?.is_suspended).toBe(true);
      expect(component.isSuspendDialogOpen()).toBe(false);
      expect(reportServiceMock.getUserCard).toHaveBeenCalledTimes(1);
      expect(text()).toContain('20/08/2026');
    });

    it('offers the button only while the account is active', () => {
      expect(component.canSuspend()).toBe(true);

      component.confirmSuspend({ hours: 48, reason: 'התנהגות פוגענית חוזרת' });
      fixture.detectChanges();

      expect(component.canSuspend()).toBe(false);
      expect(root().querySelector('app-button')).toBeNull();
    });

    it('closes the dialog without suspending on cancel', () => {
      component.openSuspendDialog();

      component.cancelSuspend();

      expect(component.isSuspendDialogOpen()).toBe(false);
      expect(reportServiceMock.suspendUser).not.toHaveBeenCalled();
    });

    it('shows the backend message when the suspension is refused', () => {
      reportServiceMock.suspendUser.mockReturnValue(
        throwError(() => ({ error: { detail: 'ניתן להשעות רק משתמש פעיל' } })),
      );
      component.openSuspendDialog();

      component.confirmSuspend({ hours: 48, reason: 'התנהגות פוגענית חוזרת' });
      fixture.detectChanges();

      expect(component.actionError()).toEqual({ key: '', text: 'ניתן להשעות רק משתמש פעיל' });
      expect(text()).toContain('ניתן להשעות רק משתמש פעיל');
      expect(component.card()?.is_suspended).toBe(false);
      expect(component.isSuspending()).toBe(false);
    });

    it('falls back to a key of ours when the failure carries no detail', () => {
      reportServiceMock.suspendUser.mockReturnValue(throwError(() => ({ error: null })));
      component.openSuspendDialog();

      component.confirmSuspend({ hours: 48, reason: 'התנהגות פוגענית חוזרת' });
      fixture.detectChanges();

      expect(component.actionError()).toEqual({
        key: 'moderator.errors.suspend_failed',
        text: '',
      });
      expect(text()).toContain('אירעה שגיאה בהשעיית המשתמש. נסי שוב.');
    });
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as the screen was written', () => {
      expect(root().querySelector('h1')!.textContent!.trim()).toBe('כרטיס משתמש');
      // The arrow is a ::before in the SCSS now, so it is not part of the text.
      expect(root().querySelector('.page__back')!.textContent!.trim()).toBe('חזרה ללוח הבקרה');
      expect(statLabels()).toEqual([
        'דיווחים נגד המשתמש/ת',
        'מהם נמצאו מוצדקים',
        'מהם נמצאו שגויים',
        'דיווחים שהגיש/ה',
        'מהם נמצאו כוזבים',
      ]);
    });

    it('leaves no Hebrew on the page in English', async () => {
      await render(makeLatinCard());

      switchToEnglish();

      expect(root().querySelector('h1')!.textContent!.trim()).toBe('User card');
      expect(statLabels()).toEqual([
        'Reports against this user',
        'Of those, found valid',
        'Of those, found invalid',
        'Reports this user filed',
        'Of those, found false',
      ]);
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The cell is two shared label keys joined in TypeScript, which the pipe
     * cannot reach. `LabelService` reads the active language, so the line
     * follows a switch — `translate()` on its own would have frozen it in the
     * language the card loaded in.
     */
    it('follows the language in the cell label, which TypeScript assembles', async () => {
      await render(makeLatinCard());
      expect(component.cellLabel()).toBe('אלמנה · חסידי');

      switchToEnglish();

      expect(component.cellLabel()).toBe('Widow · Hasidic');
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The status is one of the ten shared label maps (ABF-127), rendered
     * through the pipe with no key of this module's own — which the rename
     * below is what a private copy would hide. The cell is covered by the
     * test above: it resolves out of the same maps in both languages, and a
     * private copy could not have followed the switch.
     */
    it('takes the status from the shared constants, not its own key', () => {
      TestBed.inject(TranslocoService).setTranslationKey(
        'constants.account_status.active',
        'מצב אחר',
        { lang: 'he' },
      );
      fixture.detectChanges();

      expect(text()).toContain('מצב אחר');
      expect(text()).not.toContain('פעיל');
    });

    /**
     * The date sits in a different place in each language, so it is a
     * parameter of the sentence and not a second text node (ABF-131).
     */
    it('puts the suspension date inside the sentence, in either language', async () => {
      await render(makeLatinCard(SUSPENDED));
      expect(root().querySelector('.card__suspension')!.textContent!.trim()).toBe(
        'מושעה/ית עד 20/08/2026 12:00',
      );

      switchToEnglish();

      expect(root().querySelector('.card__suspension')!.textContent!.trim()).toBe(
        'Suspended until 20/08/2026 12:00',
      );
      expect(text()).not.toMatch(HEBREW);
    });

    /** The dialog is shared and takes finished text — the caller runs the pipe. */
    it('translates the suspend dialog through the caller, with the name as a parameter', async () => {
      await render(makeLatinCard());
      component.openSuspendDialog();
      fixture.detectChanges();
      const dialog = (): HTMLElement => root().querySelector('app-suspend-dialog')!;
      expect(dialog().textContent).toContain('השעיית Rachel Cohen למשך מספר השעות');

      switchToEnglish();

      expect(dialog().textContent).toContain('Suspend Rachel Cohen for the number of hours');
      expect(dialog().textContent).not.toMatch(HEBREW);
    });

    it('re-renders a failure of ours in the new language', async () => {
      await render(makeLatinCard());
      reportServiceMock.suspendUser.mockReturnValue(throwError(() => ({ error: null })));
      component.openSuspendDialog();
      component.confirmSuspend({ hours: 48, reason: 'Repeated abuse' });
      fixture.detectChanges();
      expect(text()).toContain('אירעה שגיאה בהשעיית המשתמש. נסי שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong suspending the user.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      const page = root().querySelector('.page') as HTMLElement;

      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });
  });
});
