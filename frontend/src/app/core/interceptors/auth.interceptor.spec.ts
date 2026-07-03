import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';

import { authInterceptor } from './auth.interceptor';
import { AuthService } from '../services/auth.service';
import type { TokenResponse } from '../models';

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let authServiceMock: {
    getAccessToken: ReturnType<typeof vi.fn>;
    refreshToken: ReturnType<typeof vi.fn>;
    clearTokens: ReturnType<typeof vi.fn>;
  };
  let routerMock: { navigate: ReturnType<typeof vi.fn> };

  const newTokens: TokenResponse = {
    access_token: 'new-token',
    refresh_token: 'new-refresh-token',
    token_type: 'bearer',
  };

  beforeEach(() => {
    authServiceMock = {
      getAccessToken: vi.fn(),
      refreshToken: vi.fn(),
      clearTokens: vi.fn(),
    };
    routerMock = { navigate: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: authServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });

    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    localStorage.clear();
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('sends the request with the Authorization header from the stored access token', () => {
    localStorage.setItem('access_token', 'abc123');

    http.get('/api/test').subscribe();

    const req = httpMock.expectOne('/api/test');
    expect(req.request.headers.get('Authorization')).toBe('Bearer abc123');
    req.flush({});
  });

  it('refreshes the token on a 401 and retries the request with the new token', () => {
    localStorage.setItem('access_token', 'expired-token');
    authServiceMock.refreshToken.mockReturnValue(of(newTokens));
    authServiceMock.getAccessToken.mockReturnValue(newTokens.access_token);

    let result: unknown;
    http.get('/api/test').subscribe((res) => (result = res));

    const firstReq = httpMock.expectOne('/api/test');
    expect(firstReq.request.headers.get('Authorization')).toBe('Bearer expired-token');
    firstReq.flush({ message: 'expired' }, { status: 401, statusText: 'Unauthorized' });

    expect(authServiceMock.refreshToken).toHaveBeenCalledTimes(1);

    const retryReq = httpMock.expectOne('/api/test');
    expect(retryReq.request.headers.get('Authorization')).toBe('Bearer new-token');
    retryReq.flush({ ok: true });

    expect(result).toEqual({ ok: true });
    expect(authServiceMock.clearTokens).not.toHaveBeenCalled();
    expect(routerMock.navigate).not.toHaveBeenCalled();
  });

  it('clears tokens and navigates to /login when refreshToken fails', () => {
    localStorage.setItem('access_token', 'expired-token');
    authServiceMock.refreshToken.mockReturnValue(
      throwError(() => ({ status: 401, statusText: 'Unauthorized' })),
    );

    let error: unknown;
    http.get('/api/test').subscribe({ error: (err) => (error = err) });

    const req = httpMock.expectOne('/api/test');
    req.flush({ message: 'expired' }, { status: 401, statusText: 'Unauthorized' });

    expect(authServiceMock.refreshToken).toHaveBeenCalledTimes(1);
    expect(authServiceMock.clearTokens).toHaveBeenCalledTimes(1);
    expect(routerMock.navigate).toHaveBeenCalledWith(['/login']);
    expect(error).toBeTruthy();
  });
  it('does not clear tokens or navigate when refreshToken fails with a non-auth error', () => {
    localStorage.setItem('access_token', 'expired-token');
    authServiceMock.refreshToken.mockReturnValue(
      throwError(() => ({ status: 500, statusText: 'Internal Server Error' })),
    );

    let error: unknown;
    http.get('/api/test').subscribe({ error: (err) => (error = err) });

    const req = httpMock.expectOne('/api/test');
    req.flush({ message: 'expired' }, { status: 401, statusText: 'Unauthorized' });

    expect(authServiceMock.refreshToken).toHaveBeenCalledTimes(1);
    expect(authServiceMock.clearTokens).not.toHaveBeenCalled();
    expect(routerMock.navigate).not.toHaveBeenCalled();
    expect(error).toEqual({ status: 500, statusText: 'Internal Server Error' });
  });
});
