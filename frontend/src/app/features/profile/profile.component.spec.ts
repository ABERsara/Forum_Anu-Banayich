/**
 * The profile screen started as a heading and five label/value rows
 * (ABF-136). ABF-117 adds SPEC §9.4/§9.5's self-service data controls: a
 * private-message retention explanation + export (USER role only — SPEC
 * §3.2's permission table), and account deletion (every role). ABF-165 adds
 * the alert address, the one profile field a user edits themselves (every
 * role).
 */

import { WritableSignal, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { Observable, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ProfileComponent } from './profile.component';
import { AccountStatus, Sector, UserRole, UserType } from '../../core/constants';
import { DirectMessageExportResult, UserProfile, UserProfileUpdate } from '../../core/models';
import { AccountService } from '../../core/services/account.service';
import { AuthService } from '../../core/services/auth.service';
import { HEBREW, translocoTesting } from '../../../testing/transloco-testing';

function makeUser(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    id: 'u1',
    first_name: 'שרה',
    last_name: 'לוי',
    email: 'sara@example.com',
    role: UserRole.USER,
    user_type: UserType.WIDOW,
    sector: Sector.SEPHARDIC,
    birth_date: null,
    account_status: AccountStatus.ACTIVE,
    alert_email: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

/** Same member with a Latin name, for the "no Hebrew leaks in English" sweep. */
function makeLatinUser(overrides: Partial<UserProfile> = {}): UserProfile {
  return makeUser({ first_name: 'Sarah', last_name: 'Levi', ...overrides });
}

function makeExportResult(): DirectMessageExportResult {
  return {
    items: [
      {
        id: 'm1',
        sender_id: 'u1',
        recipient_id: 'u2',
        content: 'שלום',
        sent_at: '2026-01-01T00:00:00Z',
        read_at: null,
      },
    ],
    total: 1,
  };
}

describe('ProfileComponent', () => {
  let fixture: ComponentFixture<ProfileComponent>;
  let authServiceMock: {
    currentUser: WritableSignal<UserProfile | null>;
    setCurrentUser: ReturnType<typeof vi.fn>;
    logout: ReturnType<typeof vi.fn>;
  };
  let accountServiceMock: {
    exportMyMessages: ReturnType<typeof vi.fn>;
    deleteMyAccount: ReturnType<typeof vi.fn>;
    updateMyProfile: ReturnType<typeof vi.fn>;
  };

  function renderFor(user: UserProfile | null): void {
    TestBed.resetTestingModule();

    // A real signal, written the way AuthService.setCurrentUser() writes it,
    // so a saved profile reaches the screen through the same path it does live.
    const currentUser = signal(user);
    authServiceMock = {
      currentUser,
      setCurrentUser: vi.fn((next: UserProfile) => currentUser.set(next)),
      logout: vi.fn(),
    };
    accountServiceMock = {
      exportMyMessages: vi.fn().mockReturnValue(of(makeExportResult())),
      deleteMyAccount: vi.fn().mockReturnValue(of(undefined)),
      // The API answers with the whole profile, the body applied to it.
      updateMyProfile: vi.fn((body: UserProfileUpdate) => of({ ...(user ?? makeUser()), ...body })),
    };

    TestBed.configureTestingModule({
      imports: [ProfileComponent, translocoTesting()],
      providers: [
        { provide: AuthService, useValue: authServiceMock },
        { provide: AccountService, useValue: accountServiceMock },
      ],
    });

    fixture = TestBed.createComponent(ProfileComponent);
    // URL.createObjectURL/revokeObjectURL don't exist in the jsdom test
    // environment — the export button triggers a real browser download,
    // which is out of scope for a component spec either way.
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock');
    URL.revokeObjectURL = vi.fn();
    fixture.detectChanges();
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function heading(): string {
    return fixture.nativeElement.querySelector('h1').textContent.trim();
  }

  /** The five profile-detail rows, whitespace normalised. */
  function detailRows(): string[] {
    return [...(fixture.nativeElement as HTMLElement).querySelectorAll('.profile-details p')].map(
      (row) => (row.textContent ?? '').replace(/\s+/g, ' ').trim(),
    );
  }

  function clickButton(text: string): void {
    const button = [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')].find(
      (btn) => btn.textContent?.trim() === text,
    );
    if (!button) throw new Error(`No button with text "${text}"`);
    button.click();
    fixture.detectChanges();
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  describe('profile details', () => {
    it('shows the signed-in member their own details', () => {
      renderFor(makeUser());

      expect(detailRows()).toEqual([
        'שם: שרה לוי',
        'מייל: sara@example.com',
        'קבוצה: אלמנה',
        'מגזר: ספרדי',
        'סטטוס: פעיל',
      ]);
    });

    it('shows the heading alone until the profile has loaded', () => {
      renderFor(null);

      expect(heading()).toBe('הפרופיל שלי');
      expect(detailRows()).toEqual([]);
      expect(fixture.nativeElement.querySelector('.profile-section')).toBeNull();
    });

    it('leaves the group and sector rows blank for a member who has neither', () => {
      renderFor(makeUser({ user_type: null, sector: null }));

      expect(detailRows()[2]).toBe('קבוצה:');
      expect(detailRows()[3]).toBe('מגזר:');
    });
  });

  describe('message export (USER role only)', () => {
    it('shows the retention explanation and export button for a plain member', () => {
      renderFor(makeUser({ role: UserRole.USER }));

      expect(text()).toContain('שמירת הודעות פרטיות');
      expect(text()).toContain('3 שנים');
      expect(
        [...fixture.nativeElement.querySelectorAll('button')].some(
          (btn: HTMLButtonElement) => btn.textContent?.trim() === 'ייצוא ההודעות שלי',
        ),
      ).toBe(true);
    });

    it.each([UserRole.ADMIN, UserRole.MODERATOR, UserRole.PROFESSIONAL])(
      'hides the export section for %s',
      (role) => {
        renderFor(makeUser({ role }));

        expect(text()).not.toContain('שמירת הודעות פרטיות');
        expect(text()).not.toContain('ייצוא ההודעות שלי');
      },
    );

    it('downloads the export and shows a success message on click', () => {
      renderFor(makeUser());

      clickButton('ייצוא ההודעות שלי');

      expect(accountServiceMock.exportMyMessages).toHaveBeenCalled();
      expect(URL.createObjectURL).toHaveBeenCalled();
      expect(text()).toContain('קובץ ההודעות ירד למחשב שלך.');
    });

    it('shows a loading state while the export request is pending', () => {
      renderFor(makeUser());
      let resolve!: (value: DirectMessageExportResult) => void;
      accountServiceMock.exportMyMessages.mockReturnValue(
        new Observable<DirectMessageExportResult>((subscriber) => {
          resolve = (value) => {
            subscriber.next(value);
            subscriber.complete();
          };
        }),
      );

      clickButton('ייצוא ההודעות שלי');

      expect(fixture.nativeElement.querySelector('.spinner')).toBeTruthy();

      resolve(makeExportResult());
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.spinner')).toBeFalsy();
    });

    it("shows the server's own message when export fails with one", () => {
      renderFor(makeUser());
      accountServiceMock.exportMyMessages.mockReturnValue(
        throwError(() => ({ error: { detail: 'אין לך הרשאה לבצע פעולה זו.' } })),
      );

      clickButton('ייצוא ההודעות שלי');

      expect(text()).toContain('אין לך הרשאה לבצע פעולה זו.');
    });

    it('falls back to a generic message when export fails without one', () => {
      renderFor(makeUser());
      accountServiceMock.exportMyMessages.mockReturnValue(throwError(() => ({ status: 500 })));

      clickButton('ייצוא ההודעות שלי');

      expect(text()).toContain('שגיאה בייצוא ההודעות');
    });
  });

  describe('account deletion (every role)', () => {
    it.each([UserRole.USER, UserRole.ADMIN, UserRole.MODERATOR, UserRole.PROFESSIONAL])(
      'shows the delete-account section for %s',
      (role) => {
        renderFor(makeUser({ role }));

        expect(text()).toContain('מחיקת חשבון');
      },
    );

    it('opens a confirmation dialog before deleting anything', () => {
      renderFor(makeUser());

      clickButton('מחיקת חשבון');

      expect(fixture.nativeElement.querySelector('app-confirm-dialog')).toBeTruthy();
      expect(accountServiceMock.deleteMyAccount).not.toHaveBeenCalled();
    });

    it('does nothing when the confirmation is cancelled', () => {
      renderFor(makeUser());
      clickButton('מחיקת חשבון');

      fixture.nativeElement
        .querySelector('app-confirm-dialog')
        .dispatchEvent(new CustomEvent('cancelled'));
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('app-confirm-dialog')).toBeNull();
      expect(accountServiceMock.deleteMyAccount).not.toHaveBeenCalled();
    });

    it('deletes the account and logs out on confirm', () => {
      renderFor(makeUser());

      fixture.componentInstance.onDeleteAccountClick();
      fixture.componentInstance.onDeleteAccountConfirmed();
      fixture.detectChanges();

      expect(accountServiceMock.deleteMyAccount).toHaveBeenCalled();
      expect(authServiceMock.logout).toHaveBeenCalled();
    });

    it("shows the server's own message when deletion fails, without logging out", () => {
      renderFor(makeUser());
      accountServiceMock.deleteMyAccount.mockReturnValue(
        throwError(() => ({ error: { detail: 'החשבון כבר נמחק' } })),
      );

      fixture.componentInstance.onDeleteAccountClick();
      fixture.componentInstance.onDeleteAccountConfirmed();
      fixture.detectChanges();

      expect(text()).toContain('החשבון כבר נמחק');
      expect(authServiceMock.logout).not.toHaveBeenCalled();
    });
  });

  describe('alert email (every role)', () => {
    function alertSection(): HTMLElement {
      const heading = (fixture.nativeElement as HTMLElement).querySelector('#alert-email-heading');
      if (!heading) throw new Error('No alert-email section');
      return heading.closest('section') as HTMLElement;
    }

    /** The read-only row, whitespace normalised — null while the field is open. */
    function alertValue(): string | null {
      const row = alertSection().querySelector('.profile-section__value');
      return row ? (row.textContent ?? '').replace(/\s+/g, ' ').trim() : null;
    }

    function alertInput(): HTMLInputElement | null {
      return alertSection().querySelector('input');
    }

    function sectionButton(label: string): HTMLButtonElement {
      const button = [...alertSection().querySelectorAll('button')].find(
        (btn) => btn.textContent?.trim() === label,
      );
      if (!button) throw new Error(`No button with text "${label}" in the alert-email section`);
      return button;
    }

    function typeAlertEmail(value: string): void {
      const input = alertInput();
      if (!input) throw new Error('The alert-email field is not open');
      input.value = value;
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    }

    function sectionText(): string {
      return (alertSection().textContent ?? '').replace(/\s+/g, ' ');
    }

    it.each([UserRole.USER, UserRole.ADMIN, UserRole.MODERATOR, UserRole.PROFESSIONAL])(
      'shows %s the current alert email on load',
      (role) => {
        renderFor(makeUser({ role, alert_email: 'alerts@example.com' }));

        expect(alertValue()).toBe('כתובת להתראות: alerts@example.com');
        expect(alertInput()).toBeNull();
      },
    );

    it('shows "לא הוגדר" when no alert email is set', () => {
      renderFor(makeUser({ alert_email: null }));

      expect(alertValue()).toBe('כתובת להתראות: לא הוגדר');
    });

    it('opens the field on the stored address and moves focus into it', async () => {
      renderFor(makeUser({ alert_email: 'alerts@example.com' }));

      clickButton('עריכה');
      await fixture.whenStable();

      expect(alertInput()?.value).toBe('alerts@example.com');
      expect(document.activeElement).toBe(alertInput());
      expect(alertValue()).toBeNull();
    });

    it('opens an empty field when nothing is set', () => {
      renderFor(makeUser({ alert_email: null }));

      clickButton('עריכה');

      expect(alertInput()?.value).toBe('');
    });

    it('saves a valid address, confirms it and shows the new value', () => {
      renderFor(makeUser({ alert_email: 'old@example.com' }));
      clickButton('עריכה');

      typeAlertEmail('new@example.com');
      clickButton('שמירה');

      expect(accountServiceMock.updateMyProfile).toHaveBeenCalledWith({
        alert_email: 'new@example.com',
      });
      expect(authServiceMock.setCurrentUser).toHaveBeenCalledWith(
        expect.objectContaining({ alert_email: 'new@example.com' }),
      );
      expect(alertInput()).toBeNull();
      expect(alertValue()).toBe('כתובת להתראות: new@example.com');
      expect(sectionText()).toContain('הכתובת להתראות עודכנה.');
    });

    it('sends the address trimmed', () => {
      renderFor(makeUser());
      clickButton('עריכה');

      typeAlertEmail('  new@example.com  ');
      clickButton('שמירה');

      expect(accountServiceMock.updateMyProfile).toHaveBeenCalledWith({
        alert_email: 'new@example.com',
      });
    });

    it('clears the address with null, and shows "לא הוגדר" after saving', () => {
      renderFor(makeUser({ alert_email: 'old@example.com' }));
      clickButton('עריכה');

      typeAlertEmail('');
      clickButton('שמירה');

      expect(accountServiceMock.updateMyProfile).toHaveBeenCalledWith({ alert_email: null });
      expect(alertValue()).toBe('כתובת להתראות: לא הוגדר');
      expect(sectionText()).toContain('הכתובת להתראות עודכנה.');
    });

    it('treats a field of spaces as cleared, not as an invalid address', () => {
      renderFor(makeUser({ alert_email: 'old@example.com' }));
      clickButton('עריכה');

      typeAlertEmail('   ');
      clickButton('שמירה');

      expect(accountServiceMock.updateMyProfile).toHaveBeenCalledWith({ alert_email: null });
    });

    it('refuses an invalid address without sending anything', () => {
      renderFor(makeUser({ alert_email: 'old@example.com' }));
      clickButton('עריכה');

      typeAlertEmail('not-an-email');
      clickButton('שמירה');

      expect(accountServiceMock.updateMyProfile).not.toHaveBeenCalled();
      expect(sectionText()).toContain('נא להזין כתובת דוא"ל תקינה');
      expect(alertInput()?.getAttribute('aria-invalid')).toBe('true');
    });

    it('cancel puts the stored address back and sends nothing', () => {
      renderFor(makeUser({ alert_email: 'old@example.com' }));
      clickButton('עריכה');
      typeAlertEmail('typed-but-not-saved@example.com');

      clickButton('ביטול');

      expect(accountServiceMock.updateMyProfile).not.toHaveBeenCalled();
      expect(alertValue()).toBe('כתובת להתראות: old@example.com');

      clickButton('עריכה');
      expect(alertInput()?.value).toBe('old@example.com');
    });

    it('returns focus to the edit button after cancel', async () => {
      renderFor(makeUser());
      clickButton('עריכה');

      clickButton('ביטול');
      await fixture.whenStable();

      expect(document.activeElement).toBe(sectionButton('עריכה'));
    });

    it('locks the form while the request is pending', () => {
      renderFor(makeUser());
      let resolve!: (value: UserProfile) => void;
      accountServiceMock.updateMyProfile.mockReturnValue(
        new Observable<UserProfile>((subscriber) => {
          resolve = (value) => {
            subscriber.next(value);
            subscriber.complete();
          };
        }),
      );
      clickButton('עריכה');
      typeAlertEmail('new@example.com');

      clickButton('שמירה');

      expect(alertSection().querySelector('.spinner')).toBeTruthy();
      expect(sectionButton('שמירה').disabled).toBe(true);
      expect(sectionButton('ביטול').disabled).toBe(true);
      expect(alertInput()?.disabled).toBe(true);

      resolve(makeUser({ alert_email: 'new@example.com' }));
      fixture.detectChanges();
      expect(alertSection().querySelector('.spinner')).toBeFalsy();
      expect(alertValue()).toBe('כתובת להתראות: new@example.com');
    });

    it('explains a 422 as an invalid address and keeps the field open', () => {
      renderFor(makeUser({ alert_email: 'old@example.com' }));
      // Validators.email lets "a@b" through; the API's EmailStr does not.
      accountServiceMock.updateMyProfile.mockReturnValue(
        throwError(() => ({ status: 422, error: { detail: [{ type: 'value_error' }] } })),
      );
      clickButton('עריכה');
      typeAlertEmail('a@b');

      clickButton('שמירה');

      expect(sectionText()).toContain('נא להזין כתובת דוא"ל תקינה');
      expect(alertInput()?.value).toBe('a@b');
      expect(alertInput()?.disabled).toBe(false);
      expect(authServiceMock.setCurrentUser).not.toHaveBeenCalled();
    });

    it("shows the server's own message when saving fails with one", () => {
      renderFor(makeUser());
      accountServiceMock.updateMyProfile.mockReturnValue(
        throwError(() => ({ status: 403, error: { detail: 'החשבון אינו פעיל.' } })),
      );
      clickButton('עריכה');
      typeAlertEmail('new@example.com');

      clickButton('שמירה');

      expect(sectionText()).toContain('החשבון אינו פעיל.');
    });

    it('falls back to a generic message when saving fails without one', () => {
      renderFor(makeUser({ alert_email: 'old@example.com' }));
      accountServiceMock.updateMyProfile.mockReturnValue(throwError(() => ({ status: 500 })));
      clickButton('עריכה');
      typeAlertEmail('new@example.com');

      clickButton('שמירה');

      expect(sectionText()).toContain('שגיאה בשמירת הכתובת להתראות');
      expect(alertInput()?.value).toBe('new@example.com');
      expect(authServiceMock.setCurrentUser).not.toHaveBeenCalled();
    });

    it('clears the previous success message when the field is opened again', () => {
      renderFor(makeUser());
      clickButton('עריכה');
      typeAlertEmail('new@example.com');
      clickButton('שמירה');

      clickButton('עריכה');

      expect(sectionText()).not.toContain('הכתובת להתראות עודכנה.');
    });
  });

  describe('i18n', () => {
    it('leaves no Hebrew on the page in English', () => {
      renderFor(makeLatinUser());

      switchToEnglish();

      expect(heading()).toBe('My profile');
      expect(detailRows()).toEqual([
        'Name: Sarah Levi',
        'Email: sara@example.com',
        'Group: Widow',
        'Sector: Sephardic',
        'Status: Active',
      ]);
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew for a role that only sees the delete-account section', () => {
      renderFor(makeLatinUser({ role: UserRole.ADMIN }));

      switchToEnglish();

      expect(text()).toContain('Delete account');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew in the alert-email section, read-only or open', () => {
      renderFor(makeLatinUser({ alert_email: null }));
      switchToEnglish();

      expect(text()).toContain('Alert email: Not set');
      expect(text()).not.toMatch(HEBREW);

      clickButton('Edit');
      expect(text()).toContain('Email address for alerts');
      expect(text()).not.toMatch(HEBREW);
    });

    it('renders the alert-email success and validation copy in English too', () => {
      renderFor(makeLatinUser());
      switchToEnglish();
      clickButton('Edit');
      const type = (value: string) => {
        const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
        input.value = value;
        input.dispatchEvent(new Event('input'));
        fixture.detectChanges();
      };

      type('not-an-email');
      clickButton('Save');
      expect(text()).toContain('Please enter a valid email address');

      type('new@example.com');
      clickButton('Save');
      expect(text()).toContain('Your alert email has been updated.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('renders the export success and error copy in English too', () => {
      renderFor(makeLatinUser());
      switchToEnglish();

      clickButton('Export my messages');

      expect(text()).toContain('Your messages file has been downloaded.');
    });
  });

  describe('layout', () => {
    /**
     * The page took its direction from an inline `direction: rtl` before
     * ABF-136, which no language switch could undo. It follows `<html dir>`
     * now.
     */
    it('does not pin its own text direction — it follows <html dir>', () => {
      renderFor(makeUser());
      const host = fixture.nativeElement as HTMLElement;
      const page = host.querySelector('.profile-page') as HTMLElement;

      expect(host.hasAttribute('dir')).toBe(false);
      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });
  });
});
