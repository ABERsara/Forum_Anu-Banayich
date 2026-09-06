import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ActiveUsersComponent } from './active-users.component';
import { AdminService } from '../../../core/services/admin.service';
import { AccountStatus, Sector, UserRole, UserType } from '../../../core/constants';
import type { UserAdminView } from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

function makeUser(overrides: Partial<UserAdminView> = {}): UserAdminView {
  return {
    id: 'u1',
    first_name: 'שרה',
    last_name: 'לוי',
    email: 'sarah@example.com',
    role: UserRole.USER,
    user_type: UserType.WIDOW,
    sector: Sector.SEPHARDIC,
    birth_date: '1985-03-15',
    account_status: AccountStatus.ACTIVE,
    created_at: '2026-06-30T04:18:27',
    phone: null,
    id_number: null,
    first_approver_id: null,
    second_approver_id: null,
    approved_at: null,
    rejection_reason: null,
    ...overrides,
  };
}

/**
 * A user whose own details carry no Hebrew.
 *
 * A person's name and email address are theirs, not UI — out of scope for
 * ABF-132 and never translated. Feeding Latin details to the `HEBREW` sweeps
 * below keeps them pointed at the copy they are meant to guard.
 */
function makeLatinUser(overrides: Partial<UserAdminView> = {}): UserAdminView {
  return makeUser({ first_name: 'Sarah', last_name: 'Levy', ...overrides });
}

describe('ActiveUsersComponent', () => {
  let fixture: ComponentFixture<ActiveUsersComponent>;
  let component: ActiveUsersComponent;
  let adminServiceMock: {
    getActiveUsers: ReturnType<typeof vi.fn>;
    suspendUser: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    adminServiceMock = {
      getActiveUsers: vi.fn().mockReturnValue(of([makeUser()])),
      suspendUser: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [ActiveUsersComponent, translocoTesting()],
      providers: [provideRouter([]), { provide: AdminService, useValue: adminServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(ActiveUsersComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('loads active users on init', () => {
    expect(component.isLoading()).toBe(false);
    expect(component.hasError()).toBe(false);
    expect(component.users().length).toBe(1);
  });

  it('sets hasError when loading fails', () => {
    adminServiceMock.getActiveUsers.mockReturnValue(throwError(() => ({})));

    component.ngOnInit();

    expect(component.hasError()).toBe(true);
    expect(component.isLoading()).toBe(false);
  });

  it('opens the suspend dialog for the clicked row', () => {
    component.suspend('u1');
    fixture.detectChanges();

    expect(component.suspendingId()).toBe('u1');
    expect(fixture.nativeElement.querySelector('app-suspend-dialog')).toBeTruthy();
  });

  it('closes the dialog without calling the service on cancel', () => {
    component.suspend('u1');
    component.cancelSuspend();

    expect(component.suspendingId()).toBeNull();
    expect(adminServiceMock.suspendUser).not.toHaveBeenCalled();
  });

  it('suspends and removes the row on success', () => {
    const updated = makeUser({ account_status: AccountStatus.SUSPENDED });
    adminServiceMock.suspendUser.mockReturnValue(of(updated));

    component.suspend('u1');
    component.confirmSuspend({ hours: 48, reason: 'הפרת כללי הפורום' });

    expect(adminServiceMock.suspendUser).toHaveBeenCalledWith('u1', 48, 'הפרת כללי הפורום');
    expect(component.users().length).toBe(0);
    expect(component.suspendingId()).toBeNull();
  });

  it('shows the backend error detail when suspend fails', () => {
    adminServiceMock.suspendUser.mockReturnValue(
      throwError(() => ({ error: { detail: 'ניתן להשעות רק משתמש פעיל' } })),
    );

    component.suspend('u1');
    component.confirmSuspend({ hours: 48, reason: 'הפרת כללי הפורום' });

    expect(component.actionError()).toEqual({ key: '', text: 'ניתן להשעות רק משתמש פעיל' });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('ניתן להשעות רק משתמש פעיל');
  });

  it('falls back to our own key when suspend fails without a detail', () => {
    adminServiceMock.suspendUser.mockReturnValue(throwError(() => ({ error: null })));

    component.suspend('u1');
    component.confirmSuspend({ hours: 48, reason: 'הפרת כללי הפורום' });

    expect(component.actionError()).toEqual({ key: 'admin.errors.suspend_failed', text: '' });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('אירעה שגיאה בהשעיית המשתמש. נסה שוב.');
  });

  it('clears a previous failure when the dialog is opened again', () => {
    adminServiceMock.suspendUser.mockReturnValue(throwError(() => ({})));
    component.suspend('u1');
    component.confirmSuspend({ hours: 48, reason: 'הפרת כללי הפורום' });

    component.suspend('u1');

    expect(component.actionError()).toEqual({ key: '', text: '' });
  });

  it('does nothing when confirmSuspend is called with no row selected', () => {
    component.confirmSuspend({ hours: 48, reason: 'הפרת כללי הפורום' });

    expect(adminServiceMock.suspendUser).not.toHaveBeenCalled();
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
    async function renderWith(getActiveUsers: ReturnType<typeof vi.fn>): Promise<void> {
      TestBed.resetTestingModule();
      adminServiceMock = { getActiveUsers, suspendUser: vi.fn() };

      await TestBed.configureTestingModule({
        imports: [ActiveUsersComponent, translocoTesting()],
        providers: [provideRouter([]), { provide: AdminService, useValue: adminServiceMock }],
      }).compileComponents();

      fixture = TestBed.createComponent(ActiveUsersComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
    }

    it('reads in Hebrew exactly as it did before the keys went in', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeUser()])));

      expect(text()).toContain('חזרה ללוח הבקרה');
      expect(heading()).toBe('משתמשים פעילים');
      expect(text()).toContain('השעה');
      expect(text()).toContain('אלמנה');
      expect(text()).toContain('ספרדי');
    });

    it('leaves no Hebrew on the page in English', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeLatinUser()])));

      switchToEnglish();

      expect(text()).toContain('Back to the dashboard');
      expect(heading()).toBe('Active users');
      expect(text()).toContain('Suspend');
      expect(text()).toContain('Widow');
      expect(text()).toContain('Sephardic');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the empty state', async () => {
      await renderWith(vi.fn().mockReturnValue(of([])));
      expect(text()).toContain('אין משתמשים פעילים כרגע.');

      switchToEnglish();

      expect(text()).toContain('There are no active users right now.');
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

    it('re-renders our own suspend failure in the new language', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeLatinUser()])));
      adminServiceMock.suspendUser.mockReturnValue(throwError(() => ({})));

      component.suspend('u1');
      component.confirmSuspend({ hours: 48, reason: 'הפרת כללי הפורום' });
      fixture.detectChanges();
      expect(text()).toContain('אירעה שגיאה בהשעיית המשתמש. נסה שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong suspending the user. Please try again.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The sentence the API wrote is not ours to translate — it stays put. */
    it('leaves the sentence the API sent exactly as it came', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeLatinUser()])));
      adminServiceMock.suspendUser.mockReturnValue(
        throwError(() => ({ error: { detail: 'ניתן להשעות רק משתמש פעיל' } })),
      );

      component.suspend('u1');
      component.confirmSuspend({ hours: 48, reason: 'הפרת כללי הפורום' });
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('ניתן להשעות רק משתמש פעיל');
    });

    /** The dialog is a shared component: it renders the text the caller hands it. */
    it('translates the copy it hands the suspend dialog', async () => {
      await renderWith(vi.fn().mockReturnValue(of([makeLatinUser()])));

      component.suspend('u1');
      fixture.detectChanges();
      expect(text()).toContain(
        'פעולה זו תשעה את המשתמש למספר השעות שנקבעו, ותשלח לו הודעה עם הסיבה.',
      );

      switchToEnglish();

      expect(text()).toContain(
        'This will suspend the user for the number of hours you set, and send them a message with the reason.',
      );
      expect(text()).not.toMatch(HEBREW);
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
