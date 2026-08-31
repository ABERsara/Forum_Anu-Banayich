/**
 * Login component.
 *
 * Design notes:
 *   - Text direction follows <html dir>, which LocaleService sets from the
 *     active language — the page does not pin its own (CONTRIBUTING §6)
 *   - Logo + site name at the top
 *   - Warm, supportive color scheme (see _variables.scss)
 */

import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { switchMap } from 'rxjs';

import { AuthError, NO_ERROR, authErrorFrom } from '../auth-error';
import { AuthService } from '../../../core/services/auth.service';
import { GoogleAuthService } from '../../../core/services/google-auth.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';
import { LoginRequest } from '../../../core/models';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
  styleUrl: './login.component.scss',
  template: `
    <div class="login-page">
      <div class="login-card">
        <h1 class="login-title">{{ 'auth.login.title' | transloco }}</h1>

        <form [formGroup]="form" (ngSubmit)="onSubmit()" novalidate>
          <div class="form-field">
            <label for="email">{{ 'auth.login.email_label' | transloco }}</label>
            <!-- dir="ltr" here is the address's own direction, not the page's:
                 an email reads left-to-right in Hebrew too. -->
            <input
              id="email"
              type="email"
              dir="ltr"
              formControlName="email"
              autocomplete="email"
              [placeholder]="'auth.login.email_placeholder' | transloco"
            />
            @if (form.controls.email.invalid && form.controls.email.touched) {
              <span class="field-error">{{ 'auth.login.email_error' | transloco }}</span>
            }
          </div>

          <div class="form-field">
            <label for="password">{{ 'auth.login.password_label' | transloco }}</label>
            <input
              id="password"
              type="password"
              formControlName="password"
              autocomplete="current-password"
              [placeholder]="'auth.login.password_placeholder' | transloco"
            />
            @if (form.controls.password.invalid && form.controls.password.touched) {
              <span class="field-error">{{ 'auth.login.password_error' | transloco }}</span>
            }
          </div>

          @if (error().text; as text) {
            <app-error-display [message]="text" />
          } @else if (error().key) {
            <app-error-display [message]="error().key | transloco" />
          }

          @if (isLoading()) {
            <app-loading-spinner [message]="'auth.login.signing_in' | transloco" />
          }

          <button type="submit" class="btn-submit" [disabled]="form.invalid || isLoading()">
            {{ 'auth.login.submit' | transloco }}
          </button>
        </form>

        <div class="divider">
          <span>{{ 'auth.login.divider' | transloco }}</span>
        </div>

        <button
          type="button"
          class="btn-google"
          [disabled]="isLoading()"
          (click)="onGoogleSignIn()"
        >
          {{ 'auth.login.google' | transloco }}
        </button>

        <p class="register-link">
          {{ 'auth.login.no_account' | transloco }}
          <a routerLink="/register">{{ 'auth.login.register_link' | transloco }}</a>
        </p>
      </div>
    </div>
  `,
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly googleAuth = inject(GoogleAuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  form = this.fb.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });

  isLoading = signal(false);
  /** What went wrong, as a key of ours or a sentence the API sent. See `AuthError`. */
  error = signal<AuthError>(NO_ERROR);

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.isLoading.set(true);
    this.error.set(NO_ERROR);

    this.auth.login(this.form.getRawValue() as LoginRequest).subscribe({
      next: () => {
        this.isLoading.set(false);
        this.router.navigate(['/home']);
      },
      error: (err) => {
        this.error.set(authErrorFrom(err, 'auth.login.error_generic'));
        this.isLoading.set(false);
      },
    });
  }

  onGoogleSignIn(): void {
    this.isLoading.set(true);
    this.error.set(NO_ERROR);

    this.googleAuth
      .signInWithGoogle()
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        switchMap((idToken) => this.auth.loginWithGoogle(idToken)),
      )
      .subscribe({
        next: () => {
          this.isLoading.set(false);
          this.router.navigate(['/home']);
        },
        error: (err) => {
          // A backend rejection (401/403/409) carries `error.detail`; anything
          // else (popup closed, network failure) is a Google/Firebase-side error.
          this.error.set(authErrorFrom(err, 'auth.login.error_google'));
          this.isLoading.set(false);
        },
      });
  }
}
