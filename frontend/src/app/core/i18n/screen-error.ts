/**
 * The failure a screen is showing, split by who wrote the sentence.
 *
 * Most requests in this app fail the same way — `err.error?.detail ?? 'Hebrew
 * fallback'` — and the two halves of that expression cannot be handled alike
 * (CONTRIBUTING §6):
 *
 *   - Our own copy is a *key*. The template runs it through the `transloco`
 *     pipe, so a message already on screen follows a language switch instead
 *     of freezing in the language it was raised in.
 *   - `error.detail` from the API — "only an active user can be suspended" —
 *     is a finished sentence, shown as it came. Swallowing it would cost the
 *     reader the one thing our generic line cannot tell them, which is *why*
 *     the request failed.
 *
 * Exactly one field is ever set; `screenErrorFrom` is the only writer, and it
 * keeps the precedence of the `??` it replaces, so no screen changed what it
 * shows for a given response.
 *
 * ```ts
 * this.error.set(screenErrorFrom(err, 'admin.errors.suspend_failed'));
 * ```
 *
 * ```html
 * @if (error().text; as text) {
 *   <app-error-display [message]="text" />
 * } @else if (error().key; as key) {
 *   <app-error-display [message]="key | transloco" />
 * }
 * ```
 *
 * **Why it lives in `core/i18n/`.** ABF-129 wrote the pair for auth, ABF-130
 * kept a local one inside `features/forum/new-post`, and ABF-131 wrote a third
 * in `features/advice` while asking the TL whether the time had come to hoist
 * it — a module's migration ticket has no business editing two other modules'
 * folders, least of all while their PRs are open for review. Admin is the
 * fourth module to want it, so this ticket puts the pair where that question
 * was already answered instead of adding a fourth copy under `features/`.
 * Folding the three existing copies into this one is a single mechanical
 * commit — a file deleted and an import re-pointed, per module — and belongs
 * to a ticket of its own, once the migration PRs above it have landed. New
 * code should import from here.
 */
export interface ScreenError {
  /** A translation key of ours, piped in the template. Empty when unused. */
  key: string;
  /** A sentence the API already wrote. Empty when unused. */
  text: string;
}

/** Nothing to show — the initial state, and what clearing an error resets to. */
export const NO_ERROR: ScreenError = { key: '', text: '' };

/**
 * A failed request, as the screen should show it: the API's own explanation
 * when it sent one, `fallbackKey` when it did not.
 */
export function screenErrorFrom(err: unknown, fallbackKey: string): ScreenError {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' && detail.trim() !== ''
    ? { key: '', text: detail }
    : { key: fallbackKey, text: '' };
}
