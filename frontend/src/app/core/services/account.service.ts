/**
 * Self-service account data controls (spec §9.4/§9.5, ABF-117).
 *
 * Split out of AuthService, whose job is login/OTP/registration and session
 * state — these are "my account" actions instead, unrelated to authenticating.
 */

import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { DirectMessageExportResult } from '../models';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class AccountService {
  private readonly api = inject(ApiService);

  /** Every private message the caller sent or received, decrypted (spec §9.5). */
  exportMyMessages(): Observable<DirectMessageExportResult> {
    return this.api.get<DirectMessageExportResult>('/users/me/messages/export');
  }

  /**
   * Delete the caller's own account (spec §9.4/UC-08): personal data is
   * scrubbed and private messages are deleted outright. Immediate — no OTP
   * step, no admin-approval queue. Does not clear local session state; the
   * caller is expected to follow a successful call with AuthService.logout().
   */
  deleteMyAccount(): Observable<void> {
    return this.api.delete<void>('/users/me');
  }
}
