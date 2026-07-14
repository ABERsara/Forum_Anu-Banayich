import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ActiveUsersComponent } from './active-users.component';
import { AdminService } from '../../../core/services/admin.service';
import { AccountStatus, Sector, UserRole, UserType } from '../../../core/constants';
import type { UserAdminView } from '../../../core/models';

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
      imports: [ActiveUsersComponent],
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

    expect(component.actionError()).toBe('ניתן להשעות רק משתמש פעיל');
  });

  it('falls back to a generic message when suspend fails without a detail', () => {
    adminServiceMock.suspendUser.mockReturnValue(throwError(() => ({ error: null })));

    component.suspend('u1');
    component.confirmSuspend({ hours: 48, reason: 'הפרת כללי הפורום' });

    expect(component.actionError()).toBe('אירעה שגיאה בהשעיית המשתמש. נסה שוב.');
  });

  it('does nothing when confirmSuspend is called with no row selected', () => {
    component.confirmSuspend({ hours: 48, reason: 'הפרת כללי הפורום' });

    expect(adminServiceMock.suspendUser).not.toHaveBeenCalled();
  });
});
