import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { PendingRegistrationsComponent } from './pending-registrations.component';
import { AdminService } from '../../../core/services/admin.service';
import { AccountStatus, DocumentType, Sector, UserRole, UserType } from '../../../core/constants';
import type { RegistrationDetail, UserAdminView } from '../../../core/models';
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

/**
 * An applicant whose own details carry no Hebrew.
 *
 * A person's name, email and the reason a document was filed are theirs, not
 * UI — out of scope for this ticket and never translated. Feeding Latin
 * details to the `HEBREW` sweeps below keeps them pointed at the copy they are
 * meant to guard.
 */
function makeLatinUser(overrides: Partial<UserAdminView> = {}): UserAdminView {
  return makeUser({ first_name: 'Sarah', last_name: 'Levy', ...overrides });
}

function makeLatinDetail(overrides: Partial<RegistrationDetail> = {}): RegistrationDetail {
  return makeDetail({ first_name: 'Sarah', last_name: 'Levy', ...overrides });
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
      imports: [PendingRegistrationsComponent, translocoTesting()],
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

  describe('the actions on a queue row', () => {
    function actionButtons(): HTMLButtonElement[] {
      return Array.from(fixture.nativeElement.querySelectorAll('.queue__actions button'));
    }

    it('names each action after the applicant it decides on', () => {
      // "אישור" on its own says nothing about whose request it approves, and
      // in a queue that is every row's button.
      expect(actionButtons().map((btn) => btn.getAttribute('aria-label'))).toEqual([
        'בדיקת הבקשה של שרה לוי',
        'אישור הבקשה של שרה לוי',
        'דחיית הבקשה של שרה לוי',
      ]);
    });

    it('opens the registration for review when its button is pressed', () => {
      const [review] = actionButtons();

      review.click();
      fixture.detectChanges();

      expect(adminServiceMock.getRegistration).toHaveBeenCalledWith('u1');
      expect(review.getAttribute('aria-expanded')).toBe('true');
      expect(review.getAttribute('aria-controls')).toBe('registration-detail-u1');
      expect(fixture.nativeElement.querySelector('#registration-detail-u1')).toBeTruthy();
    });

    it('reports the details as closed while they are', () => {
      expect(actionButtons()[0].getAttribute('aria-expanded')).toBe('false');
    });
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

    it('shows those details in English under an English locale', () => {
      component.toggleDetail('u1');
      fixture.detectChanges();

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      const text: string = fixture.nativeElement.textContent;
      expect(text).toContain('Widow');
      expect(text).toContain('Sephardic');
      expect(text).toContain('Death certificate');
      expect(text).not.toContain('אלמנה');
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

      expect(component.detailError()).toEqual({ key: '', text: 'ההרשמה אינה ממתינה לאישור' });
      expect(component.detail()).toBeNull();
      expect(fixture.nativeElement.textContent).toContain('ההרשמה אינה ממתינה לאישור');
    });

    it('falls back to a generic message when the detail request fails without one', () => {
      adminServiceMock.getRegistration.mockReturnValue(throwError(() => ({ error: null })));

      component.toggleDetail('u1');
      fixture.detectChanges();

      expect(component.detailError()).toEqual({
        key: 'admin.errors.load_registration_failed',
        text: '',
      });
      expect(component.isDetailLoading()).toBe(false);
      expect(fixture.nativeElement.textContent).toContain(
        'אירעה שגיאה בטעינת פרטי הבקשה. נסי לרענן את הדף.',
      );
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
      fixture.detectChanges();

      expect(component.actionError()).toEqual({
        key: '',
        text: 'לא ניתן לאשר את אותה הרשמה פעמיים',
      });
      expect(fixture.nativeElement.textContent).toContain('לא ניתן לאשר את אותה הרשמה פעמיים');
    });

    it('falls back to a generic message when approve fails without a detail', () => {
      adminServiceMock.approveRegistration.mockReturnValue(throwError(() => ({ error: null })));

      component.approve('u1');
      fixture.detectChanges();

      expect(component.actionError()).toEqual({ key: 'admin.errors.approve_failed', text: '' });
      expect(fixture.nativeElement.textContent).toContain('אירעה שגיאה באישור ההרשמה. נסה שוב.');
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
      fixture.detectChanges();

      expect(component.actionError()).toEqual({ key: '', text: 'ההרשמה אינה ממתינה לאישור' });
      expect(fixture.nativeElement.textContent).toContain('ההרשמה אינה ממתינה לאישור');
    });

    it('falls back to our own key when reject fails without a detail', () => {
      adminServiceMock.rejectRegistration.mockReturnValue(throwError(() => ({ error: null })));

      component.reject('u1');
      component.confirmReject('מסמכים חסרים');
      fixture.detectChanges();

      expect(component.actionError()).toEqual({ key: 'admin.errors.reject_failed', text: '' });
      expect(fixture.nativeElement.textContent).toContain('אירעה שגיאה בדחיית ההרשמה. נסה שוב.');
    });

    it('does nothing when confirmReject is called with no row selected', () => {
      component.confirmReject('מסמכים חסרים');

      expect(adminServiceMock.rejectRegistration).not.toHaveBeenCalled();
    });
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

    /**
     * Rebuilds the screen against one set of service responses. The defaults
     * carry Latin details, so the `HEBREW` sweeps below fail on our own copy
     * rather than on an applicant's name.
     */
    async function renderWith(overrides: Partial<typeof adminServiceMock> = {}): Promise<void> {
      TestBed.resetTestingModule();
      adminServiceMock = {
        getPendingRegistrations: vi.fn().mockReturnValue(of([makeLatinUser()])),
        getRegistration: vi.fn().mockReturnValue(of(makeLatinDetail())),
        approveRegistration: vi.fn(),
        rejectRegistration: vi.fn(),
        ...overrides,
      };

      await TestBed.configureTestingModule({
        imports: [PendingRegistrationsComponent, translocoTesting()],
        providers: [provideRouter([]), { provide: AdminService, useValue: adminServiceMock }],
      }).compileComponents();

      fixture = TestBed.createComponent(PendingRegistrationsComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
    }

    it('reads the queue in Hebrew exactly as it did before the keys went in', async () => {
      await renderWith({ getPendingRegistrations: vi.fn().mockReturnValue(of([makeUser()])) });

      expect(text()).toContain('חזרה ללוח הבקרה');
      expect(heading()).toBe('הרשמות ממתינות לאישור');
      expect(text()).toContain('כל הרשמה טעונה אישור של שני מנהלים');
      expect(text()).toContain('הוגשה ב-30/06/2026');
      expect(text()).toContain('ממתין לאישור מנהלים');
      expect(text()).toContain('בדיקה');
      expect(text()).toContain('אישור');
      expect(text()).toContain('דחייה');
    });

    it('leaves no Hebrew in the queue in English', async () => {
      await renderWith();

      switchToEnglish();

      expect(heading()).toBe('Registrations awaiting approval');
      expect(text()).toContain('Back to the dashboard');
      expect(text()).toContain('Every registration needs the approval of two admins');
      expect(text()).toContain('Submitted on 30/06/2026');
      expect(text()).toContain('Pending admin approval');
      expect(text()).toContain('Review');
      expect(text()).toContain('Approve');
      expect(text()).toContain('Reject');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Each row's buttons say whose request they act on, in either language. */
    it('names each action after the applicant, in the language on screen', async () => {
      await renderWith();
      const labels = (): (string | null)[] =>
        Array.from(
          (fixture.nativeElement as HTMLElement).querySelectorAll('.queue__actions button'),
        ).map((button) => button.getAttribute('aria-label'));

      expect(labels()).toEqual([
        'בדיקת הבקשה של Sarah Levy',
        'אישור הבקשה של Sarah Levy',
        'דחיית הבקשה של Sarah Levy',
      ]);

      switchToEnglish();

      expect(labels()).toEqual([
        "Review Sarah Levy's request",
        "Approve Sarah Levy's request",
        "Reject Sarah Levy's request",
      ]);
    });

    it('renames the review button once the request is open', async () => {
      await renderWith();
      component.toggleDetail('u1');
      fixture.detectChanges();
      expect(text()).toContain('סגירה');

      switchToEnglish();

      expect(text()).toContain('Close');
      expect(
        (fixture.nativeElement as HTMLElement)
          .querySelector('.queue__actions button')
          ?.getAttribute('aria-label'),
      ).toBe("Close Sarah Levy's request details");
    });

    it('reads the open request in Hebrew exactly as it did before', async () => {
      await renderWith({ getPendingRegistrations: vi.fn().mockReturnValue(of([makeUser()])) });
      component.toggleDetail('u1');
      fixture.detectChanges();

      expect(text()).toContain('טרם אושרה — נדרשים אישורים של שני מנהלים.');
      expect(text()).toContain('פרטי המבקש/ת');
      expect(text()).toContain('שם מלא');
      expect(text()).toContain('תעודת זהות');
      expect(text()).toContain('מוצגת כפי שנשמרה — הערך מוצפן במסד הנתונים.');
      expect(text()).toContain('תאריך הגשה');
      expect(text()).toContain('מסמכים שהועלו');
      expect(text()).toContain('הועלה ב-30/06/2026 04:20');
    });

    it('leaves no Hebrew in the open request in English', async () => {
      await renderWith();
      component.toggleDetail('u1');
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('Not yet approved — two admin approvals are needed.');
      expect(text()).toContain('Applicant details');
      expect(text()).toContain('Full name');
      expect(text()).toContain('ID number');
      expect(text()).toContain('Shown as it was stored — the value is encrypted in the database.');
      expect(text()).toContain('Uploaded documents');
      expect(text()).toContain('Death certificate');
      expect(text()).toContain('Uploaded on 30/06/2026 04:20');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates how far the two-admin approval got', async () => {
      await renderWith({
        getRegistration: vi.fn().mockReturnValue(
          of(
            makeLatinDetail({
              account_status: AccountStatus.PARTIALLY_APPROVED,
              first_approver_id: 'a1',
            }),
          ),
        ),
      });
      component.toggleDetail('u1');
      fixture.detectChanges();
      expect(text()).toContain('מנהל אחד כבר אישר — נדרש אישור של מנהל נוסף.');

      switchToEnglish();

      expect(text()).toContain('One admin has already approved — one more approval is needed.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates a document expiry, and the stand-in for a detail left empty', async () => {
      await renderWith({
        getRegistration: vi.fn().mockReturnValue(
          of(
            makeLatinDetail({
              phone: null,
              birth_date: null,
              documents: [
                {
                  id: 'd1',
                  doc_type: DocumentType.ID_CARD,
                  expires_on: '2030-01-31',
                  uploaded_at: '2026-06-30T04:20:00',
                },
              ],
            }),
          ),
        ),
      });
      component.toggleDetail('u1');
      fixture.detectChanges();
      expect(text()).toContain('בתוקף עד 31/01/2030');
      expect(text()).toContain('לא צוין');

      switchToEnglish();

      expect(text()).toContain('Valid until 31/01/2030');
      expect(text()).toContain('Not provided');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the empty state', async () => {
      await renderWith({ getPendingRegistrations: vi.fn().mockReturnValue(of([])) });
      expect(text()).toContain('אין הרשמות ממתינות כרגע.');

      switchToEnglish();

      expect(text()).toContain('There are no pending registrations right now.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the caption under the spinner while the queue loads', async () => {
      await renderWith({ getPendingRegistrations: vi.fn().mockReturnValue(NEVER) });
      expect(text()).toContain('טוען הרשמות...');

      switchToEnglish();

      expect(text()).toContain('Loading registrations...');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the caption under the spinner while a request loads', async () => {
      await renderWith({ getRegistration: vi.fn().mockReturnValue(NEVER) });
      component.toggleDetail('u1');
      fixture.detectChanges();
      expect(text()).toContain('טוען את פרטי הבקשה...');

      switchToEnglish();

      expect(text()).toContain('Loading the request details...');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders the load failure in the new language', async () => {
      await renderWith({
        getPendingRegistrations: vi.fn().mockReturnValue(throwError(() => ({}))),
      });
      expect(text()).toContain('אירעה שגיאה בטעינת ההרשמות. נסי לרענן את הדף.');

      switchToEnglish();

      expect(text()).toContain(
        'Something went wrong loading the registrations. Please refresh the page.',
      );
      expect(text()).not.toMatch(HEBREW);
    });

    it('re-renders our own approve failure in the new language', async () => {
      await renderWith({
        approveRegistration: vi.fn().mockReturnValue(throwError(() => ({}))),
      });

      component.approve('u1');
      fixture.detectChanges();
      expect(text()).toContain('אירעה שגיאה באישור ההרשמה. נסה שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong approving the registration.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The sentence the API wrote is not ours to translate — it stays put. */
    it('leaves the sentence the API sent exactly as it came', async () => {
      await renderWith({
        approveRegistration: vi
          .fn()
          .mockReturnValue(throwError(() => ({ error: { detail: 'ההרשמה כבר אושרה' } }))),
      });

      component.approve('u1');
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('ההרשמה כבר אושרה');
    });

    it('translates the copy it hands the reject dialog', async () => {
      await renderWith();

      component.reject('u1');
      fixture.detectChanges();
      expect(text()).toContain('דחיית הרשמה');
      expect(text()).toContain('פעולה זו תדחה את ההרשמה ותשלח למועמד הודעה עם הסיבה.');
      expect(text()).toContain('סיבת הדחייה');
      expect(placeholders()).toContain('לדוגמה: מסמכים חסרים');

      switchToEnglish();

      expect(text()).toContain('Reject registration');
      expect(text()).toContain(
        'This will reject the registration and send the applicant a message with the reason.',
      );
      expect(text()).toContain('Reason for the rejection');
      expect(placeholders()).toContain('For example: missing documents');
      expect(text()).not.toMatch(HEBREW);
    });

    /** An applicant's name and address are content, not UI: they survive the switch. */
    it('leaves what the applicant is called alone', async () => {
      await renderWith({
        getPendingRegistrations: vi.fn().mockReturnValue(of([makeUser()])),
        getRegistration: vi.fn().mockReturnValue(of(makeDetail())),
      });
      component.toggleDetail('u1');
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('שרה');
      expect(text()).toContain('לוי');
      expect(text()).toContain('sarah@example.com');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await renderWith();

      const page = fixture.nativeElement.querySelector('.page') as HTMLElement;
      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
    });

    /** Placeholders never reach `textContent`, so the sweeps above cannot see them. */
    function placeholders(): (string | null)[] {
      return Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll('input, textarea'),
      ).map((field) => field.getAttribute('placeholder'));
    }
  });
});
