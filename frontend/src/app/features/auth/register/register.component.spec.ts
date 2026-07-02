import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { RegisterComponent } from './register.component';
import { AuthService } from '../../../core/services/auth.service';

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
      imports: [RegisterComponent],
      providers: [
        provideRouter([]),
        { provide: AuthService, useValue: authService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(RegisterComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
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
      expect(component.errorMessage()).toBe('');
    });

    it('sets errorMessage and stops loading when register fails', () => {
      authService.register.mockReturnValue(
        throwError(() => ({ error: { detail: 'אימייל כבר קיים' } })),
      );

      component.submitStep2();

      expect(component.errorMessage()).toBe('אימייל כבר קיים');
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

    it('sets errorMessage when the code is wrong', () => {
      authService.verifyOtp.mockReturnValue(
        throwError(() => ({ error: { detail: 'קוד שגוי' } })),
      );

      component.submitOtp();

      expect(component.errorMessage()).toBe('קוד שגוי');
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
});
