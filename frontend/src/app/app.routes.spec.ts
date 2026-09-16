/**
 * The moderator routes, and what stops the wrong person reaching them.
 *
 * ABF-155 added `/moderator/reports/:id` and a header link into the queue, and
 * its acceptance criteria say the URL is refused to a role that may not have
 * it. Nothing tested that before: `roleGuard` had no spec, and the route table
 * had none either, so "the new route sits under the guarded parent" was true
 * only as long as nobody moved it.
 *
 * The guards are taken **off the route** rather than imported and called, so
 * what runs here is the configuration the app boots with. A detail route
 * declared as a sibling of `moderator` instead of a child of it would still
 * import cleanly, still serve the screen, and fail here.
 */

import { Injector, runInInjectionContext } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  Router,
  type ActivatedRouteSnapshot,
  type CanActivateFn,
  type RouterStateSnapshot,
} from '@angular/router';
import { vi } from 'vitest';

import { routes } from './app.routes';
import { AccountStatus, UserRole } from './core/constants';
import { authGuard } from './core/guards/auth.guard';
import { AuthService } from './core/services/auth.service';
import type { UserProfile } from './core/models';
import { ModeratorReportDetailComponent } from './features/moderator/report-detail/report-detail.component';

const ACCESS_TOKEN_KEY = 'access_token';

const moderatorRoute = routes.find((route) => route.path === 'moderator')!;
const children = moderatorRoute.children ?? [];
const detailRoute = children.find((route) => route.path === 'reports/:id');

function makeUser(role: UserRole): UserProfile {
  return {
    id: 'user-1',
    first_name: 'רחל',
    last_name: 'כהן',
    email: 'rachel@example.com',
    role,
    user_type: null,
    sector: null,
    birth_date: null,
    account_status: AccountStatus.ACTIVE,
    created_at: '2026-07-15T09:30:00',
  } as UserProfile;
}

/**
 * Runs one of the route's own guards against a signed-in user, and reports
 * both halves of the answer: whether it let the navigation through, and where
 * it sent the reader if it did not.
 */
function run(
  guard: CanActivateFn,
  user: UserProfile | null,
): { allowed: boolean; sentTo: unknown } {
  const navigate = vi.fn();

  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      { provide: AuthService, useValue: { currentUser: () => user } },
      { provide: Router, useValue: { navigate } },
    ],
  });

  const allowed = runInInjectionContext(TestBed.inject(Injector), () =>
    guard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot),
  );

  return { allowed: allowed === true, sentTo: navigate.mock.calls[0]?.[0] ?? null };
}

describe('moderator routes', () => {
  afterEach(() => localStorage.removeItem(ACCESS_TOKEN_KEY));

  it('serves the report detail screen at /moderator/reports/:id', async () => {
    expect(detailRoute).toBeDefined();

    const loaded = await (detailRoute!.loadComponent!() as Promise<unknown>);

    expect(loaded).toBe(ModeratorReportDetailComponent);
  });

  /**
   * The detail screen is guarded because it is a *child* of `moderator` — it
   * carries no `canActivate` of its own, and adding one would have been a
   * second place for the pair of roles to be written down.
   */
  it('guards it by the parent it hangs off, not by a list of its own', () => {
    expect(detailRoute!.canActivate).toBeUndefined();
    expect(moderatorRoute.canActivate).toHaveLength(2);
    expect(moderatorRoute.canActivate![0]).toBe(authGuard);
  });

  describe('the role guard on /moderator', () => {
    const roleGuardOnRoute = () => moderatorRoute.canActivate![1] as CanActivateFn;

    it.each([
      ['a moderator', UserRole.MODERATOR],
      ['an admin', UserRole.ADMIN],
    ])('lets %s through', (_who, role) => {
      expect(run(roleGuardOnRoute(), makeUser(role)).allowed).toBe(true);
    });

    /**
     * The ticket's proof of execution says a regular member typing the URL
     * "is routed to login". That is what happens to someone who is not signed
     * in — `authGuard` runs first and does exactly that, and it is pinned
     * below. A member who *is* signed in gets as far as the role guard, and
     * this is where it turns her round: to `/forum`, not to a login screen she
     * has already been through. That behaviour is `roleGuard`'s and predates
     * this ticket; what is new is that something now says so out loud.
     */
    it.each([
      ['a regular member', UserRole.USER],
      ['a professional', UserRole.PROFESSIONAL],
    ])('turns %s away, without a login screen she has already passed', (_who, role) => {
      const { allowed, sentTo } = run(roleGuardOnRoute(), makeUser(role));

      expect(allowed).toBe(false);
      expect(sentTo).toEqual(['/forum']);
    });

    it('sends a request with no user at all to the login screen', () => {
      const { allowed, sentTo } = run(roleGuardOnRoute(), null);

      expect(allowed).toBe(false);
      expect(sentTo).toEqual(['/login']);
    });
  });

  /**
   * `authGuard` runs first, and it is the one that answers the URL typed by
   * someone who is not signed in at all — before any role is known.
   */
  it('sends a visitor with no token to the login screen', () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);

    const { allowed, sentTo } = run(moderatorRoute.canActivate![0] as CanActivateFn, null);

    expect(allowed).toBe(false);
    expect(sentTo).toEqual(['/login']);
  });

  it('leaves a signed-in moderator to the role guard behind it', () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'token');

    const { allowed } = run(
      moderatorRoute.canActivate![0] as CanActivateFn,
      makeUser(UserRole.MODERATOR),
    );

    expect(allowed).toBe(true);
  });
});
