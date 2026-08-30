import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';

import { LoginComponent } from './login.component';
import { AuthService } from '../../../core/services/auth.service';
import { GoogleAuthService } from '../../../core/services/google-auth.service';
import { translocoTesting } from '../../../../testing/transloco-testing';

describe('LoginComponent', () => {
  let fixture: ComponentFixture<LoginComponent>;
  let component: LoginComponent;
  let authLoginMock: ReturnType<typeof vi.fn>;
  let authLoginWithGoogleMock: ReturnType<typeof vi.fn>;
  let googleSignInMock: ReturnType<typeof vi.fn>;
  let router: Router;

  beforeEach(async () => {
    authLoginMock = vi.fn();
    authLoginWithGoogleMock = vi.fn();
    googleSignInMock = vi.fn();

    await TestBed.configureTestingModule({
      imports: [LoginComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        {
          provide: AuthService,
          useValue: { login: authLoginMock, loginWithGoogle: authLoginWithGoogleMock },
        },
        { provide: GoogleAuthService, useValue: { signInWithGoogle: googleSignInMock } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(LoginComponent);
    component = fixture.componentInstance;
    router = TestBed.inject(Router);
    fixture.detectChanges();
  });

  it('should show field errors when submitting an empty form', () => {
    component.onSubmit();
    fixture.detectChanges();

    const errors = fixture.nativeElement.querySelectorAll('.field-error');
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should show Hebrew error and hide spinner on server error', () => {
    authLoginMock.mockReturnValue(
      throwError(() => ({ error: { detail: 'שם משתמש או סיסמה שגויים' } })),
    );
    component.form.setValue({ email: 'test@test.com', password: 'wrong' });
    component.onSubmit();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe('שם משתמש או סיסמה שגויים');
    expect(component.isLoading()).toBe(false);
    expect(fixture.nativeElement.querySelector('app-loading-spinner')).toBeNull();
  });

  it('should navigate to /home on successful login', () => {
    authLoginMock.mockReturnValue(
      of({ access_token: 't', refresh_token: 'r', token_type: 'bearer' as const }),
    );
    const navigateSpy = vi.spyOn(router, 'navigate');

    component.form.setValue({ email: 'test@example.com', password: 'Pass1234!' });
    component.onSubmit();
    fixture.detectChanges();

    expect(navigateSpy).toHaveBeenCalledWith(['/home']);
    expect(component.isLoading()).toBe(false);
  });

  it('should disable submit button while loading', () => {
    authLoginMock.mockReturnValue(new Subject());
    component.form.setValue({ email: 'test@example.com', password: 'Pass1234!' });
    component.onSubmit();
    fixture.detectChanges();

    const btn = fixture.nativeElement.querySelector('.btn-submit') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('should navigate to /home after a successful Google sign-in', () => {
    googleSignInMock.mockReturnValue(of('id-token'));
    authLoginWithGoogleMock.mockReturnValue(
      of({ access_token: 't', refresh_token: 'r', token_type: 'bearer' as const }),
    );
    const navigateSpy = vi.spyOn(router, 'navigate');

    component.onGoogleSignIn();

    expect(authLoginWithGoogleMock).toHaveBeenCalledWith('id-token');
    expect(navigateSpy).toHaveBeenCalledWith(['/home']);
    expect(component.isLoading()).toBe(false);
  });

  it('should show a Hebrew error when the Google popup fails', () => {
    googleSignInMock.mockReturnValue(throwError(() => new Error('popup closed')));

    component.onGoogleSignIn();

    expect(component.errorMessage()).toBe('הכניסה עם Google בוטלה או נכשלה.');
    expect(component.isLoading()).toBe(false);
    expect(authLoginWithGoogleMock).not.toHaveBeenCalled();
  });

  it('should show the backend error when Google login is rejected (403)', () => {
    googleSignInMock.mockReturnValue(of('id-token'));
    authLoginWithGoogleMock.mockReturnValue(
      throwError(() => ({
        error: { detail: 'אין חשבון מקושר למייל זה. יש להירשם תחילה.' },
      })),
    );

    component.onGoogleSignIn();

    expect(component.errorMessage()).toBe('אין חשבון מקושר למייל זה. יש להירשם תחילה.');
    expect(component.isLoading()).toBe(false);
  });
});
