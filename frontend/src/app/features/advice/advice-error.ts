/**
 * The failure an advice screen is showing, split by who wrote the sentence.
 *
 * Four of this module's requests fail the same way — `err.error?.detail ??
 * 'Hebrew fallback'` — and the two halves of that expression cannot be handled
 * alike (CONTRIBUTING §6):
 *
 *   - Our own copy is a *key*. The template runs it through the `transloco`
 *     pipe, so a message already on screen follows a language switch instead
 *     of freezing in the language it was raised in.
 *   - `error.detail` from the API — "the question has already been answered" —
 *     is a finished sentence, shown as-is. Swallowing it would cost the reader
 *     the one thing our generic line cannot tell them, which is *why* the
 *     request failed.
 *
 * Exactly one field is ever set; `adviceErrorFrom` is the only writer, and it
 * keeps the precedence of the `??` it replaces, so no screen changed what it
 * shows for a given response.
 *
 * This is the third copy of the pair — `features/auth/auth-error.ts` (ABF-129)
 * and a local one inside `features/forum/new-post` (ABF-130) are the other two,
 * and it is deliberately not imported from either: a module's migration ticket
 * has no business reaching into another module's folder. ABF-130's PR already
 * asked the TL whether to promote the pair to `core/i18n/` now that a third
 * module wants it; that promotion is a small mechanical change and belongs in
 * its own ticket, not inside a migration diff.
 */
export interface AdviceError {
  /** A translation key of ours, piped in the template. Empty when unused. */
  key: string;
  /** A sentence the API already wrote. Empty when unused. */
  text: string;
}

/** Nothing to show — the initial state, and what clearing an error resets to. */
export const NO_ERROR: AdviceError = { key: '', text: '' };

/**
 * A failed request, as the screen should show it: the API's own explanation
 * when it sent one, `fallbackKey` when it did not.
 */
export function adviceErrorFrom(err: unknown, fallbackKey: string): AdviceError {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' && detail.trim() !== ''
    ? { key: '', text: detail }
    : { key: fallbackKey, text: '' };
}
