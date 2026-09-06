import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { RegisterComponent } from './register.component';
import { AuthService } from '../../../core/services/auth.service';
import { DocumentType } from '../../../core/constants';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

describe('RegisterComponent', () => {
  let fixture: ComponentFixture<RegisterComponent>;
  let component: RegisterComponent;
  let authService: {
    register: ReturnType<typeof vi.fn>;
    verifyOtp: ReturnType<typeof vi.fn>;
    resendOtp: ReturnType<typeof vi.fn>;
  };

  const validStep1 = {
    first_name: 'שרה',
    last_name: 'כהן',
    id_number: '1234567',
    birth_date: '1990-01-01',
    user_type: 'widow',
    sector: 'general',
  };

  const validStep2 = {
    email: 'sara@example.com',
    phone: '0501234567',
    password: 'strongpass1',
  };

  beforeEach(async () => {
    authService = {
      register: vi.fn(),
      verifyOtp: vi.fn(),
      resendOtp: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [RegisterComponent, translocoTesting()],
      providers: [provideRouter([]), { provide: AuthService, useValue: authService }],
    }).compileComponents();

    fixture = TestBed.createComponent(RegisterComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('translates the user-type options without touching the value they submit', () => {
    const optionsOf = (field: string) =>
      Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLOptionElement>(
          `select[formControlName="${field}"] option:not([disabled])`,
        ),
      ).map((option) => [option.value, option.textContent?.trim()]);

    expect(optionsOf('user_type')).toContainEqual(['widow', 'אלמנה']);
    expect(optionsOf('sector')).toContainEqual(['sephardic', 'ספרדי']);

    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();

    // Same values, new labels — a filter or a POST built from these is unchanged.
    expect(optionsOf('user_type')).toContainEqual(['widow', 'Widow']);
    expect(optionsOf('sector')).toContainEqual(['sephardic', 'Sephardic']);
  });

  describe('isStep1Invalid', () => {
    it('is true when the step 1 fields are empty', () => {
      expect(component.isStep1Invalid()).toBe(true);
    });

    it('is false once all step 1 fields are valid', () => {
      component.form.patchValue(validStep1);
      expect(component.isStep1Invalid()).toBe(false);
    });
  });

  describe('isStep2Invalid', () => {
    it('is true when email/phone/password are empty', () => {
      expect(component.isStep2Invalid()).toBe(true);
    });

    it('is false once email/phone/password are valid', () => {
      component.form.patchValue(validStep2);
      expect(component.isStep2Invalid()).toBe(false);
    });
  });

  describe('isStep3Invalid', () => {
    it('is true when otp_code is empty', () => {
      expect(component.isStep3Invalid()).toBe(true);
    });

    it('is false once otp_code has at least 4 digits', () => {
      component.form.patchValue({ otp_code: '1234' });
      expect(component.isStep3Invalid()).toBe(false);
    });
  });

  describe('submitStep2', () => {
    beforeEach(() => {
      component.currentStep.set(2);
      component.form.patchValue({ ...validStep1, ...validStep2 });
    });

    it('calls AuthService.register with the mapped payload and advances to step 3 on success', () => {
      authService.register.mockReturnValue(of({}));

      component.submitStep2();

      expect(authService.register).toHaveBeenCalledWith({
        first_name: 'שרה',
        last_name: 'כהן',
        email: 'sara@example.com',
        phone: '0501234567',
        birth_date: '1990-01-01',
        user_type: 'widow',
        sector: 'general',
        id_number: '1234567',
        password: 'strongpass1',
      });
      expect(component.currentStep()).toBe(3);
      expect(component.isLoading()).toBe(false);
      expect(component.error()).toEqual({ key: '', text: '' });
    });

    it('shows the backend detail and stops loading when register fails', () => {
      authService.register.mockReturnValue(
        throwError(() => ({ error: { detail: 'אימייל כבר קיים' } })),
      );

      component.submitStep2();

      expect(component.error()).toEqual({ key: '', text: 'אימייל כבר קיים' });
      expect(component.isLoading()).toBe(false);
      expect(component.currentStep()).toBe(2);
    });
  });

  describe('submitOtp', () => {
    beforeEach(() => {
      component.currentStep.set(3);
      component.form.patchValue({ email: validStep2.email, otp_code: '123456' });
    });

    it('calls AuthService.verifyOtp and advances to step 4 on success', () => {
      authService.verifyOtp.mockReturnValue(of({}));

      component.submitOtp();

      expect(authService.verifyOtp).toHaveBeenCalledWith({
        email: 'sara@example.com',
        otp_code: '123456',
      });
      expect(component.currentStep()).toBe(4);
    });

    it('shows the backend detail when the code is wrong', () => {
      authService.verifyOtp.mockReturnValue(throwError(() => ({ error: { detail: 'קוד שגוי' } })));

      component.submitOtp();

      expect(component.error()).toEqual({ key: '', text: 'קוד שגוי' });
      expect(component.currentStep()).toBe(3);
    });
  });

  describe('resendOtp', () => {
    it('calls AuthService.resendOtp with the current email without changing the step', () => {
      component.currentStep.set(3);
      component.form.patchValue({ email: validStep2.email });
      authService.resendOtp.mockReturnValue(of({}));

      component.resendOtp();

      expect(authService.resendOtp).toHaveBeenCalledWith('sara@example.com');
      expect(component.currentStep()).toBe(3);
      expect(component.otpResent()).toBe(true);
    });
  });

  describe('isStep4Invalid', () => {
    beforeEach(() => {
      component.currentStep.set(4);
    });

    it('is true when no files are selected and no declarations are checked', () => {
      expect(component.isStep4Invalid()).toBe(true);
    });

    it('is true when files are selected but declarations are not all checked', () => {
      component.deathCertificateFile.set(new File([''], 'death.pdf'));
      component.selfieFile.set(new File([''], 'selfie.png'));
      component.idDocFile.set(new File([''], 'id.png'));
      component.form.patchValue({ declare_accuracy: true, declare_terms: true });

      expect(component.isStep4Invalid()).toBe(true);
    });

    it('is false once all 3 files are selected and all 3 declarations are checked', () => {
      component.deathCertificateFile.set(new File([''], 'death.pdf'));
      component.selfieFile.set(new File([''], 'selfie.png'));
      component.idDocFile.set(new File([''], 'id.png'));
      component.form.patchValue({
        declare_accuracy: true,
        declare_terms: true,
        declare_authorization: true,
      });

      expect(component.isStep4Invalid()).toBe(false);
    });
  });

  describe('setIdDocType', () => {
    it('switches the doc type and clears a previously selected file', () => {
      component.idDocFile.set(new File([''], 'id.png'));

      component.setIdDocType(DocumentType.PASSPORT);

      expect(component.idDocType()).toBe(DocumentType.PASSPORT);
      expect(component.idDocFile()).toBeNull();
    });

    it('does nothing when selecting the already-active doc type', () => {
      component.idDocFile.set(new File([''], 'id.png'));

      component.setIdDocType(DocumentType.ID_CARD);

      expect(component.idDocFile()).not.toBeNull();
    });
  });

  describe('submitStep4', () => {
    it('navigates to /auth/pending', () => {
      const router = TestBed.inject(Router);
      const navigateSpy = vi.spyOn(router, 'navigate');
      component.currentStep.set(4);

      component.submitStep4();

      expect(navigateSpy).toHaveBeenCalledWith(['/auth/pending']);
    });
  });

  describe('the copy on screen', () => {
    function text(): string {
      return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    /** Every step's fields live in one form, so a step is shown by switching to it. */
    function showStep(step: 1 | 2 | 3 | 4): void {
      component.currentStep.set(step);
      component.form.markAllAsTouched();
      fixture.detectChanges();
    }

    function switchToEnglish(): void {
      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();
    }

    describe('in Hebrew, the default', () => {
      it('reads on step 1 exactly as it did before the keys went in', () => {
        showStep(1);

        expect(fixture.nativeElement.querySelector('h1').textContent.trim()).toBe('הרשמה למערכת');
        expect(text()).toContain('שלב 1 מתוך 4');
        expect(text()).toContain('שם פרטי');
        expect(text()).toContain('שם משפחה');
        expect(text()).toContain('תעודת זהות');
        expect(text()).toContain('תאריך לידה');
        expect(text()).toContain('סוג משתמש');
        expect(text()).toContain('שיוך עדתי');
        expect(text()).toContain('בחר/י');
        expect(text()).toContain('המשך');
        expect(text()).toContain('יש לך חשבון? כנס/י כאן');
      });

      it('shows the step 1 validation messages', () => {
        showStep(1);

        expect(text()).toContain('נא להזין שם פרטי (לפחות 2 תווים)');
        expect(text()).toContain('נא להזין שם משפחה (לפחות 2 תווים)');
        expect(text()).toContain('נא להזין תעודת זהות תקינה (לפחות 7 ספרות)');
        expect(text()).toContain('נא לבחור תאריך לידה');
        expect(text()).toContain('נא לבחור סוג משתמש');
        expect(text()).toContain('נא לבחור שיוך עדתי');
      });

      it('shows step 2 and its validation messages', () => {
        showStep(2);

        expect(text()).toContain('אימייל');
        expect(text()).toContain('טלפון');
        expect(text()).toContain('סיסמה');
        expect(text()).toContain('שלח קוד OTP');
        expect(text()).toContain('נא להזין כתובת אימייל תקינה');
        expect(text()).toContain('נא להזין מספר טלפון תקין (9-15 ספרות בלבד)');
        expect(text()).toContain('הסיסמה חייבת להכיל לפחות 8 תווים');
      });

      it('shows step 3 with the address the code went to', () => {
        component.form.patchValue({ email: 'sara@example.com' });
        showStep(3);

        expect(text()).toContain('קוד אימות נשלח לאימייל: sara@example.com');
        expect(text()).toContain('נא להזין קוד אימות (לפחות 4 ספרות)');
        expect(text()).toContain('אמת/י קוד');
        expect(text()).toContain('שלח/י קוד מחדש');
      });

      it('shows step 4, with the shared document labels unchanged', () => {
        showStep(4);

        expect(text()).toContain('תעודת פטירה');
        expect(text()).toContain('תמונת סלפי');
        expect(text()).toContain('מסמך מזהה');
        expect(text()).toContain('תעודת זהות');
        expect(text()).toContain('דרכון');
        expect(text()).toContain('בחר/י תעודת פטירה');
        expect(text()).toContain('אני מצהיר/ה כי כל הפרטים והמסמכים שמסרתי נכונים ומדויקים');
        expect(text()).toContain('קראתי ואני מסכים/ה לתנאי השימוש ומדיניות הפרטיות');
        expect(text()).toContain(
          'אני מצהיר/ה כי אני זכאי/ת להירשם למערכת בהתאם לסוג המשתמש שבחרתי',
        );
        expect(text()).toContain('סיום');
      });
    });

    describe('in English', () => {
      it.each([1, 2, 3, 4] as const)('leaves no Hebrew anywhere on step %i', (step) => {
        showStep(step);

        switchToEnglish();

        expect(text()).not.toMatch(HEBREW);
      });

      it('translates step 1, its options and its validation messages', () => {
        showStep(1);

        switchToEnglish();

        expect(fixture.nativeElement.querySelector('h1').textContent.trim()).toBe('Sign up');
        expect(text()).toContain('Step 1 of 4');
        expect(text()).toContain('First name');
        expect(text()).toContain('Sector');
        expect(text()).toContain('Choose');
        expect(text()).toContain('Please enter a first name (at least 2 characters)');
        expect(text()).toContain('Please choose a sector');
        expect(text()).toContain('Continue');
        expect(text()).toContain('Already have an account? Log in here');
      });

      it('translates the step 2 validation messages', () => {
        showStep(2);

        switchToEnglish();

        expect(text()).toContain('Please enter a valid email address');
        expect(text()).toContain('Please enter a valid phone number (9-15 digits only)');
        expect(text()).toContain('The password must be at least 8 characters');
      });

      it('keeps the address in the step 3 hint while the sentence around it changes', () => {
        component.form.patchValue({ email: 'sara@example.com' });
        showStep(3);

        switchToEnglish();

        expect(text()).toContain('A verification code was sent to: sara@example.com');
        expect(text()).toContain('Please enter the verification code (at least 4 digits)');
      });

      it('translates step 4, documents and declarations alike', () => {
        showStep(4);

        switchToEnglish();

        expect(text()).toContain('Death certificate');
        expect(text()).toContain('Selfie photo');
        expect(text()).toContain('Identity document');
        expect(text()).toContain('ID card');
        expect(text()).toContain('Passport');
        expect(text()).toContain('Choose a death certificate');
        expect(text()).toContain(
          'I have read and agree to the terms of use and the privacy policy',
        );
        expect(text()).toContain('Finish');
      });

      /**
       * The failure is held as a key rather than as resolved text, so a message
       * already on screen follows the switch instead of staying in the language
       * it was raised in.
       */
      it('re-renders a failure that is already on screen', () => {
        authService.resendOtp.mockReturnValue(throwError(() => new Error('network down')));
        showStep(3);
        component.resendOtp();
        fixture.detectChanges();
        expect(text()).toContain('שליחת הקוד נכשלה.');

        switchToEnglish();

        expect(text()).toContain('Sending the code failed.');
        expect(text()).not.toMatch(HEBREW);
      });
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      expect(fixture.nativeElement.querySelector('.register-container').hasAttribute('dir')).toBe(
        false,
      );
    });
  });
});
