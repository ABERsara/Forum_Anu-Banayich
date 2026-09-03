/**
 * A confirmation this module has just raised, held as a key and the name it
 * talks about.
 *
 * Seven of the messages the two management screens show name the person the
 * action landed on — "רבקה אברמסון מונה לממונה." — so the key alone is not the
 * whole message, and `transloco.translate()` in TypeScript is not an option
 * either: it returns the text once and then goes stale, freezing a message
 * that is still on screen in the language it was raised in (CONTRIBUTING §6,
 * ABF-128). Keeping the key *and* its parameter lets the template run the pipe
 * and lets the sentence follow a language switch:
 *
 * ```ts
 * this.successMessage.set({ key: 'admin.manage_moderators.appointed', name: this.fullName(saved) });
 * ```
 *
 * ```html
 * @if (successMessage(); as message) {
 *   <p role="status">{{ message.key | transloco: { name: message.name } }}</p>
 * }
 * ```
 *
 * `null` is the empty state rather than a blank-key object like `NO_ERROR` in
 * `core/i18n/screen-error.ts`: that one is two mutually exclusive branches the
 * template reads twice, this one is a single optional value, and `@if (x; as
 * message)` reads it once.
 *
 * It lives here, next to the two screens that raise these messages, because
 * that is where a helper for one feature belongs (CONTRIBUTING §3). If a
 * second module turns out to need the same shape, that is the moment to hoist
 * it to `core/i18n/` — which is the road `screen-error.ts` took, and only
 * after the third copy.
 */
export interface ActionMessage {
  /** A translation key of ours, piped in the template. */
  key: string;
  /** The person the message is about — every message in this module names one. */
  name: string;
}
