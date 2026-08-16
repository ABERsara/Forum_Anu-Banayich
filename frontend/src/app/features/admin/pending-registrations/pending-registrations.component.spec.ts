import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { PendingRegistrationsComponent } from './pending-registrations.component';
import { AdminService } from '../../../core/services/admin.service';
import { AccountStatus, DocumentType, Sector, UserRole, UserType } from '../../../core/constants';
import type { RegistrationDetail, UserAdminView } from '../../../core/models';

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

function makeDetail(overrides: Partial<RegistrationDetail> = {}): RegistrationDetail {
  return {
    ...makeUser(),
    phone: '0501234567',
    id_number: '123456789',
    documents: [
      {
        id: 'd1',
        doc_type: DocumentType.DEATH_CERTIFICATE,
        expires_on: null,
        uploaded_at: '2026-06-30T04:20:00',
      },
    ],
    ...overrides,
  };
}

describe('PendingRegistrationsComponent', () => {
  let fixture: ComponentFixture<PendingRegistrationsComponent>;
  let component: PendingRegistrationsComponent;
  let adminServiceMock: {
    getPendingRegistrations: ReturnType<typeof vi.fn>;
    getRegistration: ReturnType<typeof vi.fn>;
    approveRegistration: ReturnType<typeof vi.fn>;
    rejectRegistration: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    adminServiceMock = {
      getPendingRegistrations: vi.fn().mockReturnValue(of([makeUser()])),
      getRegistration: vi.fn().mockReturnValue(of(makeDetail())),
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

  it('does not fetch any registration detail before one is opened', () => {
    expect(adminServiceMock.getRegistration).not.toHaveBeenCalled();
  });

  describe('reviewing a registration', () => {
    it('loads the clicked registration in full', () => {
      component.toggleDetail('u1');

      expect(adminServiceMock.getRegistration).toHaveBeenCalledWith('u1');
      expect(component.openId()).toBe('u1');
      expect(component.isDetailLoading()).toBe(false);
      expect(component.detail()?.id_number).toBe('123456789');
    });

    it('shows the details the decision rests on', () => {
      component.toggleDetail('u1');
      fixture.detectChanges();

      const text: string = fixture.nativeElement.textContent;
      expect(text).toContain('שרה לוי');
      expect(text).toContain('אלמנה');
      expect(text).toContain('ספרדי');
      expect(text).toContain('123456789');
      expect(text).toContain('0501234567');
      expect(text).toContain('30/06/2026');
    });

    it('lists the uploaded documents as metadata, with no link to open them', () => {
      component.toggleDetail('u1');
      fixture.detectChanges();

      const documents = fixture.nativeElement.querySelector('.documents');
      expect(documents.textContent).toContain('תעודת פטירה');
      expect(documents.querySelector('a')).toBeNull();
    });

    it('says so when nothing was uploaded with the request', () => {
      adminServiceMock.getRegistration.mockReturnValue(of(makeDetail({ documents: [] })));

      component.toggleDetail('u1');
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('לא הועלו מסמכים');
    });

    it('reports how far the two-admin approval got', () => {
      adminServiceMock.getRegistration.mockReturnValue(
        of(
          makeDetail({ account_status: AccountStatus.PARTIALLY_APPROVED, first_approver_id: 'a1' }),
        ),
      );

      component.toggleDetail('u1');
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('מנהל אחד כבר אישר');
    });

    it('closes the open registration when its button is clicked again', () => {
      component.toggleDetail('u1');
      component.toggleDetail('u1');

      expect(component.openId()).toBeNull();
      expect(component.detail()).toBeNull();
    });

    it('refetches on every opening, since another admin may have decided meanwhile', () => {
      component.toggleDetail('u1');
      component.toggleDetail('u1');
      component.toggleDetail('u1');

      expect(adminServiceMock.getRegistration).toHaveBeenCalledTimes(2);
    });

    it('keeps only one registration open at a time', () => {
      component.registrations.set([makeUser(), makeUser({ id: 'u2' })]);
      component.toggleDetail('u1');

      component.toggleDetail('u2');

      expect(component.openId()).toBe('u2');
      expect(adminServiceMock.getRegistration).toHaveBeenLastCalledWith('u2');
    });

    it('ignores a slow response for a registration that is no longer open', () => {
      const slowFirstRow = new Subject<RegistrationDetail>();
      adminServiceMock.getRegistration
        .mockReturnValueOnce(slowFirstRow)
        .mockReturnValueOnce(of(makeDetail({ id: 'u2', id_number: '222222222' })));
      component.registrations.set([makeUser(), makeUser({ id: 'u2' })]);
      component.toggleDetail('u1');

      component.toggleDetail('u2');
      slowFirstRow.next(makeDetail({ id: 'u1', id_number: '999999999' }));

      expect(component.openId()).toBe('u2');
      expect(component.detail()?.id).toBe('u2');
      expect(component.detail()?.id_number).toBe('222222222');
    });

    it('shows the backend message when the registration can no longer be reviewed', () => {
      adminServiceMock.getRegistration.mockReturnValue(
        throwError(() => ({ error: { detail: 'ההרשמה אינה ממתינה לאישור' } })),
      );

      component.toggleDetail('u1');
      fixture.detectChanges();

      expect(component.detailError()).toBe('ההרשמה אינה ממתינה לאישור');
      expect(component.detail()).toBeNull();
      expect(fixture.nativeElement.textContent).toContain('ההרשמה אינה ממתינה לאישור');
    });

    it('falls back to a generic message when the detail request fails without one', () => {
      adminServiceMock.getRegistration.mockReturnValue(throwError(() => ({ error: null })));

      component.toggleDetail('u1');

      expect(component.detailError()).toBe('אירעה שגיאה בטעינת פרטי הבקשה. נסי לרענן את הדף.');
      expect(component.isDetailLoading()).toBe(false);
    });
  });

  describe('approving and rejecting', () => {
    it('updates the row in place when approve leaves it partially approved', () => {
      const updated = makeUser({
        account_status: AccountStatus.PARTIALLY_APPROVED,
        first_approver_id: 'admin1',
      });
      adminServiceMock.approveRegistration.mockReturnValue(of(updated));

      component.approve('u1');

      expect(adminServiceMock.approveRegistration).toHaveBeenCalledWith('u1');
      expect(component.registrations().length).toBe(1);
      expect(component.registrations()[0].account_status).toBe(AccountStatus.PARTIALLY_APPROVED);
    });

    it('keeps the open registration in step with the approval just made', () => {
      component.toggleDetail('u1');
      adminServiceMock.approveRegistration.mockReturnValue(
        of(
          makeUser({
            account_status: AccountStatus.PARTIALLY_APPROVED,
            first_approver_id: 'admin1',
          }),
        ),
      );

      component.approve('u1');

      expect(component.detail()?.account_status).toBe(AccountStatus.PARTIALLY_APPROVED);
      expect(component.detail()?.first_approver_id).toBe('admin1');
      // The documents it already loaded are untouched by a status change.
      expect(component.detail()?.documents.length).toBe(1);
    });

    it('removes the row once approve activates the user', () => {
      const updated = makeUser({ account_status: AccountStatus.ACTIVE });
      adminServiceMock.approveRegistration.mockReturnValue(of(updated));

      component.approve('u1');

      expect(component.registrations().length).toBe(0);
    });

    it('closes the open registration once it leaves the queue', () => {
      component.toggleDetail('u1');
      adminServiceMock.approveRegistration.mockReturnValue(
        of(makeUser({ account_status: AccountStatus.ACTIVE })),
      );

      component.approve('u1');

      expect(component.openId()).toBeNull();
      expect(component.detail()).toBeNull();
    });

    it('leaves another open registration alone when a different row is decided', () => {
      component.registrations.set([makeUser(), makeUser({ id: 'u2' })]);
      component.toggleDetail('u2');
      adminServiceMock.approveRegistration.mockReturnValue(
        of(makeUser({ account_status: AccountStatus.ACTIVE })),
      );

      component.approve('u1');

      expect(component.openId()).toBe('u2');
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
      const updated = makeUser({
        account_status: AccountStatus.REJECTED,
        rejection_reason: 'מסמכים חסרים',
      });
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
});
