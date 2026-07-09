import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';

import { LoginComponent } from './login.component';
import { AuthService } from '../../../core/services/auth.service';

describe('LoginComponent', () => {
  let fixture: ComponentFixture<LoginComponent>;
  let component: LoginComponent;
  let authLoginMock: ReturnType<typeof vi.fn>;
  let router: Router;

  beforeEach(async () => {
    authLoginMock = vi.fn();

    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [provideRouter([]), { provide: AuthService, useValue: { login: authLoginMock } }],
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
});
