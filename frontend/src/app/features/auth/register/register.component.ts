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

import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Sector, UserType, SECTOR_LABELS, USER_TYPE_LABELS } from '../../../core/constants';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [RouterLink],
  template: `
    <!-- TODO: replace with real multi-step form -->
    <div style="padding: 2rem; direction: rtl">
      <h1>הרשמה למערכת</h1>
      <p>שלב {{ currentStep }} מתוך 4</p>

      @if (currentStep === 1) {
        <p>שלב 1: פרטים אישיים – TODO</p>
      }
      @if (currentStep === 2) {
        <p>שלב 2: פרטי קשר וסיסמה – TODO</p>
      }
      @if (currentStep === 3) {
        <p>שלב 3: אימות OTP – TODO</p>
      }
      @if (currentStep === 4) {
        <p>שלב 4: העלאת מסמכים – TODO</p>
      }

      <p><a routerLink="/login">יש לך חשבון? כנסי כאן</a></p>
    </div>
  `,
})
export class RegisterComponent {
  currentStep: 1 | 2 | 3 | 4 = 1;

  // Make enum values available in the template
  readonly userTypes = Object.values(UserType);
  readonly sectors = Object.values(Sector);
  readonly userTypeLabels = USER_TYPE_LABELS;
  readonly sectorLabels = SECTOR_LABELS;

  nextStep(): void {
    if (this.currentStep < 4) {
      this.currentStep = (this.currentStep + 1) as 1 | 2 | 3 | 4;
    }
  }

  prevStep(): void {
    if (this.currentStep > 1) {
      this.currentStep = (this.currentStep - 1) as 1 | 2 | 3 | 4;
    }
  }
}
