import { TestBed } from '@angular/core/testing';
import { Router, type ActivatedRouteSnapshot, type RouterStateSnapshot } from '@angular/router';

import { authGuard } from './auth.guard';
import { AccountStatus, UserRole } from '../constants';
import { AuthService } from '../services/auth.service';
import type { UserProfile } from '../models';

describe('authGuard', () => {
  let authServiceMock: { currentUser: ReturnType<typeof vi.fn> };
  let routerMock: { navigate: ReturnType<typeof vi.fn> };

  const route = {} as ActivatedRouteSnapshot;
  const state = {} as RouterStateSnapshot;

  const buildUser = (account_status: AccountStatus): UserProfile => ({
    id: 'user-1',
    first_name: 'Test',
    last_name: 'User',
    email: 'test@example.com',
    role: UserRole.USER,
    user_type: null,
    sector: null,
    birth_date: null,
    account_status,
    created_at: new Date().toISOString(),
  });

  const runGuard = () => TestBed.runInInjectionContext(() => authGuard(route, state));

  beforeEach(() => {
    authServiceMock = { currentUser: vi.fn() };
    routerMock = { navigate: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: authServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });

    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('redirects to /login when the user is not logged in', () => {
    const result = runGuard();

    expect(result).toBe(false);
    expect(routerMock.navigate).toHaveBeenCalledWith(['/login']);
  });

  it.each([AccountStatus.PENDING_APPROVAL, AccountStatus.PARTIALLY_APPROVED])(
    'redirects to /auth/pending when the user account_status is %s',
    (status) => {
      localStorage.setItem('access_token', 'valid-token');
      authServiceMock.currentUser.mockReturnValue(buildUser(status));

      const result = runGuard();

      expect(result).toBe(false);
      expect(routerMock.navigate).toHaveBeenCalledWith(['/auth/pending']);
    },
  );

  it('allows access for an active, logged-in user', () => {
    localStorage.setItem('access_token', 'valid-token');
    authServiceMock.currentUser.mockReturnValue(buildUser(AccountStatus.ACTIVE));

    const result = runGuard();

    expect(result).toBe(true);
    expect(routerMock.navigate).not.toHaveBeenCalled();
  });
});
