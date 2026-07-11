import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { PendingRegistrationsComponent } from './pending-registrations.component';
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
    account_status: AccountStatus.PENDING_APPROVAL,
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

describe('PendingRegistrationsComponent', () => {
  let fixture: ComponentFixture<PendingRegistrationsComponent>;
  let component: PendingRegistrationsComponent;
  let adminServiceMock: {
    getPendingRegistrations: ReturnType<typeof vi.fn>;
    approveRegistration: ReturnType<typeof vi.fn>;
    rejectRegistration: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    adminServiceMock = {
      getPendingRegistrations: vi.fn().mockReturnValue(of([makeUser()])),
      approveRegistration: vi.fn(),
      rejectRegistration: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [PendingRegistrationsComponent],
      providers: [provideRouter([]), { provide: AdminService, useValue: adminServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(PendingRegistrationsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('loads pending registrations on init', () => {
    expect(component.isLoading()).toBe(false);
    expect(component.hasError()).toBe(false);
    expect(component.registrations().length).toBe(1);
  });

  it('sets hasError when loading fails', () => {
    adminServiceMock.getPendingRegistrations.mockReturnValue(throwError(() => ({})));

    component.ngOnInit();

    expect(component.hasError()).toBe(true);
    expect(component.isLoading()).toBe(false);
  });

  it('updates the row in place when approve leaves it partially approved', () => {
    const updated = makeUser({ account_status: AccountStatus.PARTIALLY_APPROVED, first_approver_id: 'admin1' });
    adminServiceMock.approveRegistration.mockReturnValue(of(updated));

    component.approve('u1');

    expect(adminServiceMock.approveRegistration).toHaveBeenCalledWith('u1');
    expect(component.registrations().length).toBe(1);
    expect(component.registrations()[0].account_status).toBe(AccountStatus.PARTIALLY_APPROVED);
  });

  it('removes the row once approve activates the user', () => {
    const updated = makeUser({ account_status: AccountStatus.ACTIVE });
    adminServiceMock.approveRegistration.mockReturnValue(of(updated));

    component.approve('u1');

    expect(component.registrations().length).toBe(0);
  });

  it('shows the backend error detail when approve fails', () => {
    adminServiceMock.approveRegistration.mockReturnValue(
      throwError(() => ({ error: { detail: 'לא ניתן לאשר את אותה הרשמה פעמיים' } })),
    );

    component.approve('u1');

    expect(component.actionError()).toBe('לא ניתן לאשר את אותה הרשמה פעמיים');
  });

  it('falls back to a generic message when approve fails without a detail', () => {
    adminServiceMock.approveRegistration.mockReturnValue(throwError(() => ({ error: null })));

    component.approve('u1');

    expect(component.actionError()).toBe('אירעה שגיאה באישור ההרשמה. נסה שוב.');
  });

  it('opens the confirm dialog for the clicked row on reject', () => {
    component.reject('u1');
    fixture.detectChanges();

    expect(component.rejectingId()).toBe('u1');
    expect(fixture.nativeElement.querySelector('app-confirm-dialog')).toBeTruthy();
  });

  it('closes the dialog without calling the service on cancel', () => {
    component.reject('u1');
    component.cancelReject();

    expect(component.rejectingId()).toBeNull();
    expect(adminServiceMock.rejectRegistration).not.toHaveBeenCalled();
  });

  it('rejects with the given reason and removes the row on success', () => {
    const updated = makeUser({ account_status: AccountStatus.REJECTED, rejection_reason: 'מסמכים חסרים' });
    adminServiceMock.rejectRegistration.mockReturnValue(of(updated));

    component.reject('u1');
    component.confirmReject('מסמכים חסרים');

    expect(adminServiceMock.rejectRegistration).toHaveBeenCalledWith('u1', 'מסמכים חסרים');
    expect(component.registrations().length).toBe(0);
    expect(component.rejectingId()).toBeNull();
  });

  it('shows the backend error detail when reject fails', () => {
    adminServiceMock.rejectRegistration.mockReturnValue(
      throwError(() => ({ error: { detail: 'ההרשמה אינה ממתינה לאישור' } })),
    );

    component.reject('u1');
    component.confirmReject('מסמכים חסרים');

    expect(component.actionError()).toBe('ההרשמה אינה ממתינה לאישור');
  });

  it('does nothing when confirmReject is called with no row selected', () => {
    component.confirmReject('מסמכים חסרים');

    expect(adminServiceMock.rejectRegistration).not.toHaveBeenCalled();
  });
});
