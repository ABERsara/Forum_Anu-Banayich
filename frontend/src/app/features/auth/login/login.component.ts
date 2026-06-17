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

import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <!-- TODO: replace with real template -->
    <div style="padding: 2rem; text-align: center; direction: rtl">
      <h1>כניסה למערכת</h1>
      <p>TODO: implement login form</p>
      <p><a routerLink="/register">אין לך חשבון? הירשם/י כאן</a></p>
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

  isLoading = false;
  errorMessage = '';

  onSubmit(): void {
    if (this.form.invalid) return;

    this.isLoading = true;
    this.errorMessage = '';

    // TODO: implement
    // this.auth.login(this.form.value as LoginRequest).subscribe({
    //   next: () => this.router.navigate(['/forum']),
    //   error: (err) => {
    //     this.errorMessage = err.error?.detail ?? 'שגיאה בכניסה. בדקי את הפרטים.';
    //     this.isLoading = false;
    //   },
    // });
  }
}
