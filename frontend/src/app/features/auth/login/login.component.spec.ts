import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';

import { LoginComponent } from './login.component';
import { AuthService } from '../../../core/services/auth.service';
import { GoogleAuthService } from '../../../core/services/google-auth.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

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

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  it('should show field errors when submitting an empty form', () => {
    component.onSubmit();
    fixture.detectChanges();

    const errors = fixture.nativeElement.querySelectorAll('.field-error');
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should show the backend detail and hide the spinner on server error', () => {
    authLoginMock.mockReturnValue(
      throwError(() => ({ error: { detail: 'שם משתמש או סיסמה שגויים' } })),
    );
    component.form.setValue({ email: 'test@test.com', password: 'wrong' });
    component.onSubmit();
    fixture.detectChanges();

    expect(component.error()).toEqual({ key: '', text: 'שם משתמש או סיסמה שגויים' });
    expect(text()).toContain('שם משתמש או סיסמה שגויים');
    expect(component.isLoading()).toBe(false);
    expect(fixture.nativeElement.querySelector('app-loading-spinner')).toBeNull();
  });

  it('should fall back to our own message when the server sends no detail', () => {
    authLoginMock.mockReturnValue(throwError(() => new Error('network down')));
    component.form.setValue({ email: 'test@test.com', password: 'wrong' });
    component.onSubmit();
    fixture.detectChanges();

    expect(component.error()).toEqual({ key: 'auth.login.error_generic', text: '' });
    expect(text()).toContain('שגיאה בכניסה. בדוק/י את הפרטים.');
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

  it('should show our own message when the Google popup fails', () => {
    googleSignInMock.mockReturnValue(throwError(() => new Error('popup closed')));

    component.onGoogleSignIn();
    fixture.detectChanges();

    expect(component.error()).toEqual({ key: 'auth.login.error_google', text: '' });
    expect(text()).toContain('הכניסה עם Google בוטלה או נכשלה.');
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
    fixture.detectChanges();

    expect(component.error()).toEqual({
      key: '',
      text: 'אין חשבון מקושר למייל זה. יש להירשם תחילה.',
    });
    expect(text()).toContain('אין חשבון מקושר למייל זה. יש להירשם תחילה.');
    expect(component.isLoading()).toBe(false);
  });

  describe('in Hebrew, the default', () => {
    it('reads exactly as it did before the keys went in', () => {
      expect(fixture.nativeElement.querySelector('.login-title').textContent.trim()).toBe(
        'כניסה למערכת',
      );
      expect(text()).toContain('אימייל');
      expect(text()).toContain('סיסמה');
      expect(text()).toContain('כניסה');
      expect(text()).toContain('או');
      expect(text()).toContain('התחבר עם Google');
      expect(text()).toContain('אין לך חשבון?');
      expect(text()).toContain('הירשם/י כאן');
    });

    it('shows the field errors in Hebrew', () => {
      component.onSubmit();
      fixture.detectChanges();

      expect(text()).toContain('נא להזין כתובת אימייל תקינה');
      expect(text()).toContain('נא להזין סיסמה');
    });

    it('captions the spinner in Hebrew while the request is in flight', () => {
      authLoginMock.mockReturnValue(new Subject());
      component.form.setValue({ email: 'test@example.com', password: 'Pass1234!' });
      component.onSubmit();
      fixture.detectChanges();

      expect(text()).toContain('מתחבר/ת...');
    });
  });

  describe('in English', () => {
    it('translates the page, the Google button and the divider', () => {
      switchToEnglish();

      expect(fixture.nativeElement.querySelector('.login-title').textContent.trim()).toBe('Log in');
      expect(text()).toContain('Email');
      expect(text()).toContain('Password');
      expect(text()).toContain('Sign in with Google');
      expect(text()).toContain('or');
      expect(text()).toContain("Don't have an account?");
      expect(text()).toContain('Sign up here');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the field errors too', () => {
      component.onSubmit();
      switchToEnglish();

      expect(text()).toContain('Please enter a valid email address');
      expect(text()).toContain('Please enter a password');
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The failure is held as a key rather than as resolved text, so a message
     * already on screen follows the switch instead of staying in the language
     * it was raised in.
     */
    it('re-renders a failure that is already on screen', () => {
      googleSignInMock.mockReturnValue(throwError(() => new Error('popup closed')));
      component.onGoogleSignIn();
      fixture.detectChanges();
      expect(text()).toContain('הכניסה עם Google בוטלה או נכשלה.');

      switchToEnglish();

      expect(text()).toContain('Google sign-in was cancelled or failed.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('captions the spinner in English', () => {
      authLoginMock.mockReturnValue(new Subject());
      component.form.setValue({ email: 'test@example.com', password: 'Pass1234!' });
      component.onSubmit();
      switchToEnglish();

      expect(text()).toContain('Signing in...');
      expect(text()).not.toMatch(HEBREW);
    });
  });

  it('does not pin its own text direction — it follows <html dir>', () => {
    expect(fixture.nativeElement.querySelector('.login-page').hasAttribute('dir')).toBe(false);
  });
});
