/**
 * The failure an auth screen is showing, split by who wrote the sentence.
 *
 * Login and register both raise errors from two sources, and the two cannot be
 * handled the same way:
 *
 *   - Our own copy — "wrong code", "sign-in failed" — is a *key*. The template
 *     runs it through the `transloco` pipe, so a message already on screen
 *     follows a language switch instead of freezing in the language it was
 *     raised in (CONTRIBUTING §6).
 *   - `error.detail` from the API — "this email is already registered" — is a
 *     finished sentence. It is shown as-is: swallowing it would cost the reader
 *     the one thing our generic fallback cannot tell them, which is *why* the
 *     request failed.
 *
 * The API still writes those sentences in Hebrew whatever the UI language; it
 * speaks translation keys only for direct messages so far (`errors.*`, ABF-118).
 * Making it speak them for `/auth/*` too is a backend change, not this ticket.
 */
export interface AuthError {
  /** A translation key of ours, piped in the template. Empty when unused. */
  key: string;
  /** A sentence the API or a shared component already resolved. Empty when unused. */
  text: string;
}

/** Nothing to show — the initial state, and what clearing an error resets to. */
export const NO_ERROR: AuthError = { key: '', text: '' };

/**
 * A failed request, as the screen should show it: the API's own explanation
 * when it sent one, `fallbackKey` when it did not.
 *
 * Same precedence as the `err.error?.detail ?? '...'` this replaced, so no
 * screen changed what it shows for a given response.
 */
export function authErrorFrom(err: unknown, fallbackKey: string): AuthError {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' && detail.trim() !== ''
    ? { key: '', text: detail }
    : { key: fallbackKey, text: '' };
}
