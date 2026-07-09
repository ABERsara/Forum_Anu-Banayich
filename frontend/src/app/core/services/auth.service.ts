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

import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap, throwError } from 'rxjs';

import {
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

  constructor() {
    // On app startup: if a token exists, load the current user profile
    if (this.getAccessToken()) {
      this.loadCurrentUser().subscribe({
        error: () => this.clearTokens(),
      });
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
    return this.api.post<TokenResponse>('/auth/login', data).pipe(
      tap((tokens) => {
        this.saveTokens(tokens);
        // if profile load fails after login, clear tokens to avoid a half-authenticated state
        this.loadCurrentUser().subscribe({
          error: () => this.clearTokens(),
        });
      }),
    );
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
    return this.api.post<TokenResponse>('/auth/refresh', { refresh_token }).pipe(
      tap(tokens => this.saveTokens(tokens)),
    );
  }

  // ──────────────────────────────────────────────────────────
  // Current user
  // ──────────────────────────────────────────────────────────

  loadCurrentUser(): Observable<UserProfile> {
    return this.api.get<UserProfile>('/users/me').pipe(
      tap(user => this._currentUser.set(user)),
    );
  }
}
