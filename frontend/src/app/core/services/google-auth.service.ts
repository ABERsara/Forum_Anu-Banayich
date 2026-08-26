/**
 * Wraps the Firebase JS SDK's Google sign-in popup.
 *
 * Talks to Google/Firebase only — never to our backend. Returns the signed
 * Firebase ID token, which AuthService then sends to POST /auth/google for
 * verification and JWT issuance.
 */

import { Injectable } from '@angular/core';
import { getApp, getApps, initializeApp } from 'firebase/app';
import { GoogleAuthProvider, getAuth, signInWithPopup } from 'firebase/auth';
import { Observable, from, switchMap } from 'rxjs';

import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class GoogleAuthService {
  // Avoid Firebase's "duplicate-app" error if this service is ever
  // re-instantiated (HMR, tests) while an app instance already exists.
  private readonly app = getApps().length ? getApp() : initializeApp(environment.firebase);
  private readonly auth = getAuth(this.app);

  /** Opens the Google sign-in popup and resolves with a Firebase ID token. */
  signInWithGoogle(): Observable<string> {
    return from(signInWithPopup(this.auth, new GoogleAuthProvider())).pipe(
      switchMap((result) => from(result.user.getIdToken())),
    );
  }
}
