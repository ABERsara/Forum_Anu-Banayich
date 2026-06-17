/**
 * Role-based route guard.
 *
 * Usage in routes:
 *   canActivate: [authGuard, roleGuard(UserRole.ADMIN)]
 *
 * The authGuard must run first to ensure the user is logged in.
 */

import { inject } from '@angular/core';
import { Router, type CanActivateFn } from '@angular/router';

import { UserRole } from '../constants';
import { AuthService } from '../services/auth.service';

export function roleGuard(...allowedRoles: UserRole[]): CanActivateFn {
  return () => {
    const auth = inject(AuthService);
    const router = inject(Router);

    const user = auth.currentUser();
    if (!user) {
      router.navigate(['/login']);
      return false;
    }

    if (allowedRoles.includes(user.role)) {
      return true;
    }

    // Redirect to home if not authorized
    router.navigate(['/forum']);
    return false;
  };
}
