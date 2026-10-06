/**
 * What this guard has to get right is *when* it decides, not only what it
 * decides. The role it checks lives on a profile that arrives over the
 * network, so every case below fixes the order of the two: a profile that is
 * already in, one that is still on its way, and one that never came.
 */

import { TestBed } from '@angular/core/testing';
import { Router, type ActivatedRouteSnapshot, type RouterStateSnapshot } from '@angular/router';
import { Observable, Subject, firstValueFrom, isObservable, of } from 'rxjs';

import { roleGuard } from './role.guard';
import { AccountStatus, UserRole } from '../constants';
import { AuthService } from '../services/auth.service';
import type { UserProfile } from '../models';

describe('roleGuard', () => {
  let authServiceMock: {
    authResolved: Observable<void>;
    currentUser: ReturnType<typeof vi.fn>;
    getAccessToken: ReturnType<typeof vi.fn>;
  };
  let routerMock: { navigate: ReturnType<typeof vi.fn> };

  const route = {} as ActivatedRouteSnapshot;
  const state = {} as RouterStateSnapshot;

  const buildUser = (role: UserRole): UserProfile => ({
    id: 'user-1',
    first_name: 'Test',
    last_name: 'User',
    email: 'test@example.com',
    role,
    user_type: null,
    sector: null,
    birth_date: null,
    account_status: AccountStatus.ACTIVE,
    created_at: new Date().toISOString(),
  });

  /** Runs the guard and unwraps the observable it returns. */
  const runGuard = (...allowed: UserRole[]): Promise<boolean> => {
    const result = TestBed.runInInjectionContext(() => roleGuard(...allowed)(route, state));
    if (!isObservable(result)) throw new Error('the guard is expected to decide asynchronously');
    return firstValueFrom(result as Observable<boolean>);
  };

  beforeEach(() => {
    authServiceMock = {
      authResolved: of(undefined),
      currentUser: vi.fn().mockReturnValue(null),
      getAccessToken: vi.fn().mockReturnValue(null),
    };
    routerMock = { navigate: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: authServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });
  });

  it('allows a user whose role is in the list', async () => {
    authServiceMock.currentUser.mockReturnValue(buildUser(UserRole.PROFESSIONAL));
    authServiceMock.getAccessToken.mockReturnValue('valid-token');

    await expect(runGuard(UserRole.PROFESSIONAL)).resolves.toBe(true);
    expect(routerMock.navigate).not.toHaveBeenCalled();
  });

  it('sends a user in another role to /forum', async () => {
    authServiceMock.currentUser.mockReturnValue(buildUser(UserRole.USER));
    authServiceMock.getAccessToken.mockReturnValue('valid-token');

    await expect(runGuard(UserRole.ADMIN)).resolves.toBe(false);
    expect(routerMock.navigate).toHaveBeenCalledWith(['/forum']);
  });

  it('waits for the profile instead of refusing while it is still loading', async () => {
    // The cold-load order: the guard runs first, the profile lands after it.
    const resolved = new Subject<void>();
    authServiceMock.authResolved = resolved.asObservable();
    authServiceMock.getAccessToken.mockReturnValue('valid-token');

    const decision = runGuard(UserRole.ADMIN);

    expect(routerMock.navigate).not.toHaveBeenCalled();

    authServiceMock.currentUser.mockReturnValue(buildUser(UserRole.ADMIN));
    resolved.next();

    await expect(decision).resolves.toBe(true);
    expect(routerMock.navigate).not.toHaveBeenCalled();
  });

  it('lets a session the server never judged through to the screen', async () => {
    // The profile load failed without a verdict, so the token still stands.
    authServiceMock.getAccessToken.mockReturnValue('valid-token');

    await expect(runGuard(UserRole.ADMIN)).resolves.toBe(true);
    expect(routerMock.navigate).not.toHaveBeenCalled();
  });

  it('sends a caller with no session at all to /login', async () => {
    await expect(runGuard(UserRole.ADMIN)).resolves.toBe(false);
    expect(routerMock.navigate).toHaveBeenCalledWith(['/login']);
  });
});
