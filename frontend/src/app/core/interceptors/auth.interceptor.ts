import { Injector, inject } from '@angular/core';
import { HttpInterceptorFn } from '@angular/common/http';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

/**
 * Attaches the token, and refreshes it once on a 401.
 *
 * `AuthService` is resolved through an injector rather than injected here,
 * and only on the 401 path. Injecting it outright made every request issued
 * *by* `AuthService` fail: its own constructor loads the profile, so the
 * interceptor asked for the service while that constructor was still running
 * and Angular answered with NG0200 (circular dependency). The request never
 * reached the network, the load "failed", and the session was cleared on
 * every cold page load. By the time a 401 comes back, the service exists.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const injector = inject(Injector);
  const router = inject(Router);
  const token = localStorage.getItem('access_token');
  const authReq = token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

  return next(authReq).pipe(
    catchError((err) => {
      if (err.status !== 401 || req.url.includes('/auth/refresh')) return throwError(() => err);

      const auth = injector.get(AuthService);
      return auth.refreshToken().pipe(
        switchMap(() => {
          const newToken = auth.getAccessToken();
          if (!newToken) {
            return throwError(() => new Error('No token after refresh'));
          }
          return next(req.clone({ setHeaders: { Authorization: `Bearer ${newToken}` } }));
        }),
        catchError((refreshErr) => {
          if (refreshErr.status === 401 || refreshErr.status === 403) {
            auth.clearTokens();
            router.navigate(['/login']);
          }
          return throwError(() => refreshErr);
        }),
      );
    }),
  );
};
