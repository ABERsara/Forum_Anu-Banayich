/**
 * The startup profile load, and what it is allowed to do to the session.
 *
 * The service pulls `GET /users/me` as soon as it is constructed, and used to
 * clear the tokens on any failure of that call. A cold page load is the only
 * thing that runs it, which is why a reload - and only a reload - signed the
 * user out whenever the backend was unreachable. The cases below pin the line
 * between a refusal by the server and a request that never got an answer.
 */

import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { firstValueFrom, timeout } from 'rxjs';

import { AuthService } from './auth.service';
import { authInterceptor } from '../interceptors/auth.interceptor';
import { environment } from '../../../environments/environment';
import { AccountStatus, UserRole } from '../constants';
import type { UserProfile } from '../models';

const PROFILE: UserProfile = {
  id: 'user-1',
  first_name: 'Test',
  last_name: 'User',
  email: 'test@example.com',
  alert_email: null,
  role: UserRole.USER,
  user_type: null,
  sector: null,
  birth_date: null,
  account_status: AccountStatus.ACTIVE,
  created_at: '2026-10-05T09:00:00Z',
};

describe('AuthService startup profile load', () => {
  let httpMock: HttpTestingController;
  const routerMock = { navigate: vi.fn() };

  /**
   * Builds the service, which is what fires the request. The token has to be
   * in place before that, exactly as it is on a real page load.
   */
  const startWithToken = (token: string | null): AuthService => {
    if (token) {
      localStorage.setItem('access_token', token);
      localStorage.setItem('refresh_token', 'refresh-token');
    }
    const service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
    return service;
  };

  const profileRequest = () => httpMock.expectOne(`${environment.apiUrl}/users/me`);

  /** The replayed value of `authResolved`, rejecting if it never comes. */
  const authResolved = (service: AuthService): Promise<void> =>
    firstValueFrom(service.authResolved.pipe(timeout(100)));

  beforeEach(() => {
    localStorage.clear();
    routerMock.navigate.mockClear();

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: Router, useValue: routerMock },
      ],
    });
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('keeps the session when the backend is not answering at all', () => {
    const service = startWithToken('valid-token');

    profileRequest().error(new ProgressEvent('error'));

    expect(service.getAccessToken()).toBe('valid-token');
    expect(service.getRefreshToken()).toBe('refresh-token');
  });

  it('keeps the session when the server fails with a 500', () => {
    const service = startWithToken('valid-token');

    profileRequest().flush('boom', { status: 500, statusText: 'Internal Server Error' });

    expect(service.getAccessToken()).toBe('valid-token');
  });

  it.each([401, 403])('ends the session when the server refuses it with a %i', (status) => {
    const service = startWithToken('valid-token');

    profileRequest().flush('no', { status, statusText: 'Refused' });

    expect(service.getAccessToken()).toBeNull();
    expect(service.getRefreshToken()).toBeNull();
    expect(service.currentUser()).toBeNull();
  });

  it('resolves the auth state once the profile is in', async () => {
    const service = startWithToken('valid-token');

    profileRequest().flush(PROFILE);

    await expect(authResolved(service)).resolves.toBeUndefined();
    expect(service.currentUser()).toEqual(PROFILE);
    expect(service.isLoggedIn()).toBe(true);
  });

  it('resolves the auth state immediately when there is no token to check', async () => {
    const service = startWithToken(null);

    await expect(authResolved(service)).resolves.toBeUndefined();
    expect(service.currentUser()).toBeNull();
  });

  it('resolves the auth state even where the load failed, so no guard is left waiting', async () => {
    const service = startWithToken('valid-token');

    profileRequest().error(new ProgressEvent('error'));

    await expect(authResolved(service)).resolves.toBeUndefined();
  });

  it('marks the profile unavailable when the load failed without a refusal', () => {
    const service = startWithToken('valid-token');

    profileRequest().error(new ProgressEvent('error'));

    // The screens have a token and no profile: they show a connection error
    // rather than a spinner nothing will ever stop.
    expect(service.profileUnavailable()).toBe(true);
  });

  it('does not mark it unavailable when the server refused the session', () => {
    const service = startWithToken('valid-token');

    profileRequest().flush('no', { status: 401, statusText: 'Unauthorized' });

    expect(service.profileUnavailable()).toBe(false);
  });

  it('clears the flag once a retry brings the profile in', () => {
    const service = startWithToken('valid-token');
    profileRequest().error(new ProgressEvent('error'));

    service.reloadProfile();
    profileRequest().flush(PROFILE);

    expect(service.profileUnavailable()).toBe(false);
    expect(service.currentUser()).toEqual(PROFILE);
  });
});

/**
 * The startup load, with the interceptor the app actually runs it through.
 *
 * Every case above provides `HttpClient` bare, and that is what let the bug
 * live: `authInterceptor` used to `inject(AuthService)` at its top, so the
 * request the *constructor* makes asked Angular for a service that was still
 * being constructed. NG0200 came back instead of a response, nothing reached
 * the network, and the old `error: () => clearTokens()` signed the user out on
 * every cold page load. A spec without the interceptor cannot see any of it.
 */
describe('AuthService through the app interceptor chain', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('access_token', 'valid-token');

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigate: vi.fn() } },
      ],
    });
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('sends the startup request, and keeps the session, instead of failing in the injector', () => {
    const service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);

    httpMock.expectOne(`${environment.apiUrl}/users/me`).flush(PROFILE);

    expect(service.currentUser()).toEqual(PROFILE);
    expect(service.profileUnavailable()).toBe(false);
    expect(service.getAccessToken()).toBe('valid-token');
  });
});
