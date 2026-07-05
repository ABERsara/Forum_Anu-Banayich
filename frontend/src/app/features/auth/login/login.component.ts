/**
 * Login component.
 *
 * TODO:
 *   1. Build the login form using Angular Reactive Forms
 *      Fields: email (required, email validator), password (required)
 *   2. On submit: call AuthService.login()
 *   3. Show error message if login fails (wrong credentials / account not active)
 *   4. Show loading spinner during the request
 *   5. Add a link to /register for new users
 *
 * Design notes:
 *   - RTL layout (Hebrew)
 *   - Logo + site name at the top
 *   - Warm, supportive color scheme (see _variables.scss)
 */

import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../../core/services/auth.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';
import { LoginRequest } from '../../../core/models';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, ErrorDisplayComponent, LoadingSpinnerComponent],
  styleUrl: './login.component.scss',
  template: `
    <div class="login-page" dir="rtl">
      <div class="login-card">
        <h1 class="login-title">כניסה למערכת</h1>

        <form [formGroup]="form" (ngSubmit)="onSubmit()" novalidate>

          <div class="form-field">
            <label for="email">אימייל</label>
            <input
              id="email"
              type="email"
              dir="ltr"
              formControlName="email"
              autocomplete="email"
              placeholder="your@email.com"
            />
            @if (form.controls.email.invalid && form.controls.email.touched) {
              <span class="field-error">נא להזין כתובת אימייל תקינה</span>
            }
          </div>

          <div class="form-field">
            <label for="password">סיסמה</label>
            <input
              id="password"
              type="password"
              formControlName="password"
              autocomplete="current-password"
              placeholder="סיסמה"
            />
            @if (form.controls.password.invalid && form.controls.password.touched) {
              <span class="field-error">נא להזין סיסמה</span>
            }
          </div>

          <app-error-display [message]="errorMessage()" />

          @if (isLoading()) {
            <app-loading-spinner message="מתחבר/ת..." />
          }

          <button
            type="submit"
            class="btn-submit"
            [disabled]="form.invalid || isLoading()"
          >
            כניסה
          </button>

        </form>

        <p class="register-link">
          אין לך חשבון? <a routerLink="/register">הירשם/י כאן</a>
        </p>
      </div>
    </div>
  `,
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  form = this.fb.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });

  isLoading = signal(false);
  errorMessage = signal('');

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set('');

    this.auth.login(this.form.getRawValue() as LoginRequest).subscribe({
      next: () => {
        this.isLoading.set(false);
        this.router.navigate(['/home']);
      },
      error: (err) => {
        this.errorMessage.set(err.error?.detail ?? 'שגיאה בכניסה. בדוק/י את הפרטים.');
        this.isLoading.set(false);
      },
    });

  }
}
