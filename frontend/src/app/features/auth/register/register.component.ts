/**
 * Multi-step registration component.
 *
 * The registration flow has 4 steps (מסך רב-שלבי):
 *
 *   Step 1 – Personal details
 *     first_name, last_name, id_number, birth_date, user_type, sector
 *
 *   Step 2 – Contact & password
 *     email, phone, password
 *     → After submit: OTP is sent to email
 *
 *   Step 3 – OTP verification
 *     Enter the 6-digit code received by email
 *
 *   Step 4 – Document upload
 *     death_certificate (required), selfie (required), id_card OR passport (required)
 *
 *   After step 4: show "your request is pending admin approval" message
 *
 * TODO:
 *   1. Build a reactive form with all fields
 *   2. Use a step tracker (currentStep: 1 | 2 | 3 | 4)
 *   3. Validate each step before proceeding
 *   4. Call AuthService.register() after step 2
 *   5. Call AuthService.verifyOtp() in step 3
 *   6. Implement file upload in step 4 (multipart/form-data to backend)
 *   7. Show progress bar or step indicators at the top
 */

import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { Sector, UserType, SECTOR_LABELS, USER_TYPE_LABELS } from '../../../core/constants';
import { AuthService } from '../../../core/services/auth.service';
import { RegisterRequest, OtpVerifyRequest } from '../../../core/models';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';


@Component({
  selector: 'app-register',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, ErrorDisplayComponent, LoadingSpinnerComponent],
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss',
})
export class RegisterComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  currentStep = signal<1 | 2 | 3 | 4>(1);

  form = this.fb.group({
    first_name: ['', [Validators.required, Validators.minLength(2)]],
    last_name: ['', [Validators.required, Validators.minLength(2)]],
    id_number: ['', [Validators.required, Validators.minLength(7)]],
    birth_date: ['', Validators.required],
    user_type: ['', Validators.required],
    sector: ['', Validators.required],

    email: ['', [Validators.required, Validators.email]],
    phone: ['', [Validators.required, Validators.pattern(/^\d{9,15}$/)]],
    password: ['', [Validators.required, Validators.minLength(8)]],

    otp_code: ['', [Validators.required, Validators.minLength(4)]],
  });

  isLoading = signal(false);
  errorMessage = signal('');
  otpResent = signal(false);

  isStep1Invalid(): boolean {
    const fields = ['first_name', 'last_name', 'id_number', 'birth_date', 'user_type', 'sector'];
    return fields.some(f => this.form.get(f)!.invalid);
  }

  isStep2Invalid(): boolean {
    const fields = ['email', 'phone', 'password'];
    return fields.some(f => this.form.get(f)!.invalid);
  }

  isStep3Invalid(): boolean {
    return this.form.get('otp_code')!.invalid;
  }

  submitStep2(): void {
    this.errorMessage.set('');
    this.isLoading.set(true);

    const payload: RegisterRequest = {
      first_name: this.form.value.first_name!,
      last_name: this.form.value.last_name!,
      email: this.form.value.email!,
      phone: this.form.value.phone!,
      birth_date: this.form.value.birth_date!,
      user_type: this.form.value.user_type as UserType,
      sector: this.form.value.sector as Sector,
      id_number: this.form.value.id_number!,
      password: this.form.value.password!,
    };

    this.auth.register(payload).subscribe({
      next: () => {
        this.isLoading.set(false);
        this.nextStep();
      },
      error: (err) => {
        this.isLoading.set(false);
        this.errorMessage.set(err.error?.detail ?? 'שגיאה בהרשמה. נסה/י שוב.');
      },
    });
  }

  submitOtp(): void {
    this.errorMessage.set('');
    this.otpResent.set(false);
    this.isLoading.set(true);

    const payload: OtpVerifyRequest = {
      email: this.form.value.email!,
      otp_code: this.form.value.otp_code!,
    };

    this.auth.verifyOtp(payload).subscribe({
      next: () => {
        this.isLoading.set(false);
        this.nextStep();
      },
      error: (err) => {
        this.isLoading.set(false);
        this.errorMessage.set(err.error?.detail ?? 'קוד שגוי. נסה/י שוב.');
      },
    });
  }

  resendOtp(): void {
    this.errorMessage.set('');
    this.otpResent.set(false);
    this.isLoading.set(true);

    this.auth.resendOtp(this.form.value.email!).subscribe({
      next: () => {
        this.isLoading.set(false);
        this.otpResent.set(true);
      },
      error: (err) => {
        this.isLoading.set(false);
        this.errorMessage.set(err.error?.detail ?? 'שליחת הקוד נכשלה.');
      },
    });
  }

  // Make enum values available in the template
  readonly userTypes = Object.values(UserType);
  readonly sectors = Object.values(Sector);
  readonly userTypeLabels = USER_TYPE_LABELS;
  readonly sectorLabels = SECTOR_LABELS;

  nextStep(): void {
    if (this.currentStep() < 4) {
      this.currentStep.update(s => (s + 1) as 1 | 2 | 3 | 4);
    }
  }

  prevStep(): void {
    if (this.currentStep() > 1) {
      this.currentStep.update(s => (s - 1) as 1 | 2 | 3 | 4);
    }
  }
}
