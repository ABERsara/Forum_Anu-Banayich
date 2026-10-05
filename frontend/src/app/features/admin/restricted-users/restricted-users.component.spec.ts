import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { RestrictedUsersComponent } from './restricted-users.component';
import { AdminService } from '../../../core/services/admin.service';
import { AccountStatus, UserRole } from '../../../core/constants';
import type { UserAdminView } from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

function makeUser(overrides: Partial<UserAdminView> = {}): UserAdminView {
  return {
    id: 'u1',
    first_name: 'שרה',
    last_name: 'לוי',
    email: 'sarah@example.com',
    role: UserRole.USER,
    user_type: null,
    sector: null,
    birth_date: '1985-03-15',
    account_status: AccountStatus.ACTIVE,
    created_at: '2026-06-30T04:18:27',
    phone: null,
    id_number: null,
    first_approver_id: null,
    second_approver_id: null,
    approved_at: null,
    rejection_reason: null,
    is_report_restricted: true,
    ...overrides,
  };
}

/**
 * A user whose own details carry no Hebrew.
 *
 * A person's name and email address are theirs, not UI — never translated.
 * Feeding Latin details to the `HEBREW` sweeps below keeps them pointed at
 * the copy they are meant to guard.
 */
function makeLatinUser(overrides: Partial<UserAdminView> = {}): UserAdminView {
  return makeUser({ first_name: 'Sarah', last_name: 'Levy', ...overrides });
}

describe('RestrictedUsersComponent', () => {
  let fixture: ComponentFixture<RestrictedUsersComponent>;
  let component: RestrictedUsersComponent;
  let adminServiceMock: {
    getRestrictedUsers: ReturnType<typeof vi.fn>;
    liftRestriction: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    adminServiceMock = {
      getRestrictedUsers: vi.fn().mockReturnValue(of([makeUser()])),
      liftRestriction: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [RestrictedUsersComponent, translocoTesting()],
      providers: [provideRouter([]), { provide: AdminService, useValue: adminServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(RestrictedUsersComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('loads restricted users on init', () => {
    expect(component.isLoading()).toBe(false);
    expect(component.hasError()).toBe(false);
    expect(component.users().length).toBe(1);
  });

  it('sets hasError when loading fails', () => {
    adminServiceMock.getRestrictedUsers.mockReturnValue(throwError(() => ({})));

    component.ngOnInit();

    expect(component.hasError()).toBe(true);
    expect(component.isLoading()).toBe(false);
  });

  it('opens the confirm dialog for the clicked row', () => {
    component.lift('u1');
    fixture.detectChanges();

    expect(component.liftingId()).toBe('u1');
    expect(fixture.nativeElement.querySelector('app-confirm-dialog')).toBeTruthy();
  });

  it('closes the dialog without calling the service on cancel', () => {
    component.lift('u1');
    component.cancelLift();

    expect(component.liftingId()).toBeNull();
    expect(adminServiceMock.liftRestriction).not.toHaveBeenCalled();
  });

  it('lifts the restriction and removes the row on success', () => {
    const updated = makeUser({ is_report_restricted: false });
    adminServiceMock.liftRestriction.mockReturnValue(of(updated));

    component.lift('u1');
    component.confirmLift();

    expect(adminServiceMock.liftRestriction).toHaveBeenCalledWith('u1');
    expect(component.users().length).toBe(0);
    expect(component.liftingId()).toBeNull();
  });

  it('shows the backend error detail when lifting fails', () => {
    adminServiceMock.liftRestriction.mockReturnValue(
      throwError(() => ({ error: { detail: 'למשתמש זה אין הגבלת דיווח פעילה' } })),
    );

    component.lift('u1');
    component.confirmLift();

    expect(component.actionError()).toEqual({
      key: '',
      text: 'למשתמש זה אין הגבלת דיווח פעילה',
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('למשתמש זה אין הגבלת דיווח פעילה');
  });

  it('falls back to our own key when lifting fails without a detail', () => {
    adminServiceMock.liftRestriction.mockReturnValue(throwError(() => ({ error: null })));

    component.lift('u1');
    component.confirmLift();

    expect(component.actionError()).toEqual({
      key: 'admin.errors.lift_restriction_failed',
      text: '',
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('אירעה שגיאה בהסרת ההגבלה. נסה שוב.');
  });

  it('closes the dialog on failure, so the error underneath is visible', () => {
    adminServiceMock.liftRestriction.mockReturnValue(throwError(() => ({})));

    component.lift('u1');
    component.confirmLift();

    expect(component.liftingId()).toBeNull();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('app-confirm-dialog')).toBeFalsy();
  });

  it('clears a previous failure when the dialog is opened again', () => {
    adminServiceMock.liftRestriction.mockReturnValue(throwError(() => ({})));
    component.lift('u1');
    component.confirmLift();

    component.lift('u1');

    expect(component.actionError()).toEqual({ key: '', text: '' });
  });

  it('does nothing when confirmLift is called with no row selected', () => {
    component.confirmLift();

    expect(adminServiceMock.liftRestriction).not.toHaveBeenCalled();
  });

  describe('i18n', () => {
    function text(): string {
      return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    function heading(): string {
      return fixture.nativeElement.querySelector('h1').textContent.trim();
    }

    function switchToEnglish(): void {
      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();
    }

    /** Rebuilds the screen against one service response. */
    async function renderWith(getRestrictedUsers: ReturnType<typeof vi.fn>): Promise<void> {
      TestBed.resetTestingModule();
      adminServiceMock = { getRestrictedUsers, liftRestriction: vi.fn() };

      await TestBed.configureTestingModule({
        imports: [RestrictedUsersComponent, translocoTesting()],
        providers: [provideRouter([]), { provide: AdminService, useValue: adminServiceMock }],
      }).compileComponents();

      fixture = TestBed.createComponent(RestrictedUsersComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
    }

    it('reads in Hebrew exactly as it did before the keys went in', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeUser()])));

      expect(text()).toContain('חזרה ללוח הבקרה');
      expect(heading()).toBe('משתמשים מוגבלי דיווח');
      expect(text()).toContain('הסר הגבלה');
    });

    it('leaves no Hebrew on the page in English', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeLatinUser()])));

      switchToEnglish();

      expect(text()).toContain('Back to the dashboard');
      expect(heading()).toBe('Report-restricted users');
      expect(text()).toContain('Lift restriction');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the empty state', async () => {
      await renderWith(vi.fn().mockReturnValue(of([])));
      expect(text()).toContain('אין משתמשים מוגבלי דיווח כרגע.');

      switchToEnglish();

      expect(text()).toContain('There are no report-restricted users right now.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders the load failure in the new language', async () => {
      await renderWith(vi.fn().mockReturnValue(throwError(() => ({}))));
      expect(text()).toContain('אירעה שגיאה בטעינת המשתמשים. נסה לרענן את הדף.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong loading the users. Please refresh the page.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('re-renders our own lift failure in the new language', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeLatinUser()])));
      adminServiceMock.liftRestriction.mockReturnValue(throwError(() => ({})));

      component.lift('u1');
      component.confirmLift();
      fixture.detectChanges();
      expect(text()).toContain('אירעה שגיאה בהסרת ההגבלה. נסה שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong lifting the restriction. Please try again.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The sentence the API wrote is not ours to translate — it stays put. */
    it('leaves the sentence the API sent exactly as it came', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeLatinUser()])));
      adminServiceMock.liftRestriction.mockReturnValue(
        throwError(() => ({ error: { detail: 'למשתמש זה אין הגבלת דיווח פעילה' } })),
      );

      component.lift('u1');
      component.confirmLift();
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('למשתמש זה אין הגבלת דיווח פעילה');
    });

    /** The dialog is a shared component: it renders the text the caller hands it. */
    it('translates the copy it hands the confirm dialog', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeLatinUser()])));

      component.lift('u1');
      fixture.detectChanges();
      expect(text()).toContain('המשתמש יוכל להגיש דיווחים מחדש.');

      switchToEnglish();

      expect(text()).toContain('The user will be able to file reports again.');
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The confirm button's own label is a separate [confirmText] binding, not
     * the generic "שלח"/"Confirm" fallback — a deleted binding would only be
     * caught here, since the row button carries the same words too.
     */
    it('passes its own label to the confirm button, not the generic fallback', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeLatinUser()])));

      component.lift('u1');
      fixture.detectChanges();
      const confirmButton = fixture.nativeElement.querySelector(
        'app-confirm-dialog .btn--primary',
      ) as HTMLElement;
      expect(confirmButton.textContent?.trim()).toBe('הסר הגבלה');

      switchToEnglish();

      const confirmButtonEn = fixture.nativeElement.querySelector(
        'app-confirm-dialog .btn--primary',
      ) as HTMLElement;
      expect(confirmButtonEn.textContent?.trim()).toBe('Lift restriction');
    });

    /** A person's name and address are content, not UI: they survive the switch. */
    it('leaves what the user is called alone', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeUser()])));

      switchToEnglish();

      expect(text()).toContain('שרה');
      expect(text()).toContain('לוי');
      expect(text()).toContain('sarah@example.com');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeUser()])));

      const page = fixture.nativeElement.querySelector('.page') as HTMLElement;
      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });

    it('leaves no Hebrew on the page while the list is still loading', async () => {
      await renderWith(vi.fn().mockReturnValue(NEVER));

      switchToEnglish();

      expect(fixture.nativeElement.querySelector('app-loading-spinner')).toBeTruthy();
      expect(text()).not.toMatch(HEBREW);
    });
  });
});
