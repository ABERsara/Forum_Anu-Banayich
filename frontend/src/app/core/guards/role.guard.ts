/**
 * Role-based route guard.
 *
 * Usage in routes:
 *   canActivate: [authGuard, roleGuard(UserRole.ADMIN)]
 *
 * The authGuard must run first to ensure the user is logged in.
 *
 * The role lives on the profile, which arrives over the network, so the guard
 * waits for `authResolved` before it decides. Deciding straight away is what
 * made every reload of a role screen land on `/login`: the guard and the
 * `GET /users/me` that fills the profile start in the same tick, and the
 * guard always won. Navigating inside a running app was unaffected, which is
 * why only reloads and typed-in addresses failed.
 */

import { inject } from '@angular/core';
import { Router, type CanActivateFn } from '@angular/router';
import { map, take } from 'rxjs';

import { UserRole } from '../constants';
import { AuthService } from '../services/auth.service';

export function roleGuard(...allowedRoles: UserRole[]): CanActivateFn {
  return () => {
    const auth = inject(AuthService);
    const router = inject(Router);

    return auth.authResolved.pipe(
      take(1),
      map(() => {
        const user = auth.currentUser();

        if (user) {
          if (allowedRoles.includes(user.role)) {
            return true;
          }

          // Redirect to home if not authorized
          router.navigate(['/forum']);
          return false;
        }

        if (!auth.getAccessToken()) {
          router.navigate(['/login']);
          return false;
        }

        // A session the server never got to judge: the profile load failed
        // without a verdict (backend down, 5xx, CORS). The session stands, so
        // she goes through to a screen that will show its own loading error
        // rather than to a login page she does not need - and the role is
        // still enforced on every request the screen makes.
        return true;
      }),
    );
  };
}
