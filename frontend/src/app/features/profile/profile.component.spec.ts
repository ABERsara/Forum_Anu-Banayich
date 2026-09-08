/**
 * The profile screen started as a heading and five label/value rows
 * (ABF-136). ABF-117 adds SPEC §9.4/§9.5's self-service data controls: a
 * private-message retention explanation + export (USER role only — SPEC
 * §3.2's permission table), and account deletion (every role).
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { Observable, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ProfileComponent } from './profile.component';
import { AccountStatus, Sector, UserRole, UserType } from '../../core/constants';
import { DirectMessageExportResult, UserProfile } from '../../core/models';
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
    currentUser: ReturnType<typeof vi.fn>;
    exportMyMessages: ReturnType<typeof vi.fn>;
    deleteMyAccount: ReturnType<typeof vi.fn>;
    logout: ReturnType<typeof vi.fn>;
  };

  function renderFor(user: UserProfile | null): void {
    TestBed.resetTestingModule();

    authServiceMock = {
      currentUser: vi.fn().mockReturnValue(user),
      exportMyMessages: vi.fn().mockReturnValue(of(makeExportResult())),
      deleteMyAccount: vi.fn().mockReturnValue(of(undefined)),
      logout: vi.fn(),
    };

    TestBed.configureTestingModule({
      imports: [ProfileComponent, translocoTesting()],
      providers: [{ provide: AuthService, useValue: authServiceMock }],
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

      expect(authServiceMock.exportMyMessages).toHaveBeenCalled();
      expect(URL.createObjectURL).toHaveBeenCalled();
      expect(text()).toContain('קובץ ההודעות ירד למחשב שלך.');
    });

    it('shows a loading state while the export request is pending', () => {
      renderFor(makeUser());
      let resolve!: (value: DirectMessageExportResult) => void;
      authServiceMock.exportMyMessages.mockReturnValue(
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
      authServiceMock.exportMyMessages.mockReturnValue(
        throwError(() => ({ error: { detail: 'אין לך הרשאה לבצע פעולה זו.' } })),
      );

      clickButton('ייצוא ההודעות שלי');

      expect(text()).toContain('אין לך הרשאה לבצע פעולה זו.');
    });

    it('falls back to a generic message when export fails without one', () => {
      renderFor(makeUser());
      authServiceMock.exportMyMessages.mockReturnValue(throwError(() => ({ status: 500 })));

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
      expect(authServiceMock.deleteMyAccount).not.toHaveBeenCalled();
    });

    it('does nothing when the confirmation is cancelled', () => {
      renderFor(makeUser());
      clickButton('מחיקת חשבון');

      fixture.nativeElement
        .querySelector('app-confirm-dialog')
        .dispatchEvent(new CustomEvent('cancelled'));
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('app-confirm-dialog')).toBeNull();
      expect(authServiceMock.deleteMyAccount).not.toHaveBeenCalled();
    });

    it('deletes the account and logs out on confirm', () => {
      renderFor(makeUser());

      fixture.componentInstance.onDeleteAccountClick();
      fixture.componentInstance.onDeleteAccountConfirmed();
      fixture.detectChanges();

      expect(authServiceMock.deleteMyAccount).toHaveBeenCalled();
      expect(authServiceMock.logout).toHaveBeenCalled();
    });

    it("shows the server's own message when deletion fails, without logging out", () => {
      renderFor(makeUser());
      authServiceMock.deleteMyAccount.mockReturnValue(
        throwError(() => ({ error: { detail: 'החשבון כבר נמחק' } })),
      );

      fixture.componentInstance.onDeleteAccountClick();
      fixture.componentInstance.onDeleteAccountConfirmed();
      fixture.detectChanges();

      expect(text()).toContain('החשבון כבר נמחק');
      expect(authServiceMock.logout).not.toHaveBeenCalled();
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
