import { inject } from '@angular/core';
import { HttpInterceptorFn } from '@angular/common/http';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const token = localStorage.getItem('access_token');
  const authReq = token
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(authReq).pipe(
    catchError(err => {
      if (err.status !== 401 || req.url.includes('/auth/refresh')) return throwError(() => err);

      return auth.refreshToken().pipe(
        switchMap(() => {
          const newToken = auth.getAccessToken() ?? '';
          return next(req.clone({ setHeaders: { Authorization: `Bearer ${newToken}` } }));
        }),
        catchError(() => {
          auth.clearTokens();
          router.navigate(['/login']);
          return throwError(() => err);
        })
      );
    })
  );
};
