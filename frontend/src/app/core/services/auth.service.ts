/**
 * Authentication service.
 *
 * Manages login, registration, JWT storage, and current user state.
 *
 * TODO list for junior developer:
 *   [x] implement register() – POST /auth/register
 *   [x] implement verifyOtp() – POST /auth/verify-otp
 *   [x] implement login() – POST /auth/login, save tokens, load profile
 *   [x] implement logout() – clear tokens
 *   [x] implement refreshToken() – call /auth/refresh on 401
 */

import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, ReplaySubject, tap, throwError } from 'rxjs';

import {
  GoogleAuthRequest,
  LoginRequest,
  OtpVerifyRequest,
  RegisterRequest,
  TokenResponse,
  UserProfile,
} from '../models';
import { UserRole } from '../constants';
import { ApiService } from './api.service';

const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  // Reactive state – components read from these signals
  private readonly _currentUser = signal<UserProfile | null>(null);

  readonly currentUser = this._currentUser.asReadonly();
  readonly isLoggedIn = computed(() => this._currentUser() !== null);
  readonly isUser = computed(() => this._currentUser()?.role === UserRole.USER);
  readonly isAdmin = computed(() => this._currentUser()?.role === UserRole.ADMIN);
  readonly isModerator = computed(() => this._currentUser()?.role === UserRole.MODERATOR);
  readonly isProfessional = computed(() => this._currentUser()?.role === UserRole.PROFESSIONAL);

  private readonly _profileUnavailable = signal(false);

  /**
   * True once the startup profile load has failed *without* the server
   * refusing the session: the token still stands, but nobody knows yet who
   * she is. A screen that renders from the profile shows a connection error
   * and a retry instead of a spinner that would never stop turning.
   */
  readonly profileUnavailable = this._profileUnavailable.asReadonly();

  private readonly resolved = new ReplaySubject<void>(1);

  /**
   * Emits once the startup profile load has settled - loaded, rejected or
   * failed - and replays that to anyone who asks later.
   *
   * A route guard that needs the profile waits for this instead of racing it:
   * on a cold page load the guard runs in the same tick that sends
   * `GET /users/me`, so reading `currentUser()` there only ever saw `null`.
   */
  readonly authResolved = this.resolved.asObservable();

  constructor() {
    // On app startup: if a token exists, load the current user profile
    if (this.getAccessToken()) {
      this.loadCurrentUser().subscribe({
        next: () => this.resolved.next(),
        error: (err: unknown) => this.onProfileLoadFailed(err),
      });
    } else {
      this.resolved.next();
    }
  }

  // ──────────────────────────────────────────────────────────
  // Registration flow
  // ──────────────────────────────────────────────────────────

  register(data: RegisterRequest): Observable<unknown> {
    return this.api.post('/auth/register', data);
  }

  verifyOtp(data: OtpVerifyRequest): Observable<unknown> {
    return this.api.post('/auth/verify-otp', data);
  }

  resendOtp(email: string): Observable<unknown> {
    return this.api.post('/auth/resend-otp', { email });
  }

  // ──────────────────────────────────────────────────────────
  // Login / logout
  // ──────────────────────────────────────────────────────────

  login(data: LoginRequest): Observable<TokenResponse> {
    return this.api
      .post<TokenResponse>('/auth/login', data)
      .pipe(tap((tokens) => this.loadProfileAfterTokens(tokens)));
  }

  loginWithGoogle(idToken: string): Observable<TokenResponse> {
    const body: GoogleAuthRequest = { id_token: idToken };
    return this.api
      .post<TokenResponse>('/auth/google', body)
      .pipe(tap((tokens) => this.loadProfileAfterTokens(tokens)));
  }

  /** Stores a fresh pair of tokens and pulls the profile they belong to. */
  private loadProfileAfterTokens(tokens: TokenResponse): void {
    this.saveTokens(tokens);
    this.loadCurrentUser().subscribe({
      error: (err: unknown) => this.onProfileLoadFailed(err),
    });
  }

  /**
   * A failed profile load ends the session only where the server actually
   * refused the credentials.
   *
   * A 401 arrives here having already been through the refresh attempt in
   * `authInterceptor`, so it means the refresh was refused too. Anything else
   * - a backend that is not up (status 0), a 5xx, a CORS failure - says
   * nothing about the token. Clearing it there signed a user out on every
   * cold load the backend happened to miss, and every reload landed on
   * `/login` with a perfectly valid session in hand.
   */
  private onProfileLoadFailed(err: unknown): void {
    const refused = err instanceof HttpErrorResponse && (err.status === 401 || err.status === 403);

    if (refused) {
      this.clearTokens();
    }
    // A refusal is a logout, and the screens for that are the login ones. It
    // is the other kind of failure that leaves a screen with nothing to show.
    this._profileUnavailable.set(!refused);
    this.resolved.next();
  }

  /** Retries the load behind the connection error the screens are showing. */
  reloadProfile(): void {
    this._profileUnavailable.set(false);
    this.loadCurrentUser().subscribe({
      error: (err: unknown) => this.onProfileLoadFailed(err),
    });
  }

  logout(): void {
    this.clearTokens();
    this.router.navigate(['/login']);
  }

  // ──────────────────────────────────────────────────────────
  // Token management
  // ──────────────────────────────────────────────────────────

  getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  }

  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  }

  saveTokens(tokens: TokenResponse): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  }

  clearTokens(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    this._currentUser.set(null);
  }

  refreshToken(): Observable<TokenResponse> {
    const refresh_token = this.getRefreshToken();
    if (!refresh_token) return throwError(() => new Error('No refresh token available'));
    return this.api
      .post<TokenResponse>('/auth/refresh', { refresh_token })
      .pipe(tap((tokens) => this.saveTokens(tokens)));
  }

  // ──────────────────────────────────────────────────────────
  // Current user
  // ──────────────────────────────────────────────────────────

  loadCurrentUser(): Observable<UserProfile> {
    return this.api.get<UserProfile>('/users/me').pipe(
      tap((user) => {
        this._currentUser.set(user);
        this._profileUnavailable.set(false);
      }),
    );
  }

  /**
   * Replace the signed-in user's profile with one the API just returned, e.g.
   * after the user edited it (PUT /users/me answers with the whole profile),
   * so every screen reading currentUser shows the saved value without a
   * second GET.
   */
  setCurrentUser(user: UserProfile): void {
    this._currentUser.set(user);
  }
}
