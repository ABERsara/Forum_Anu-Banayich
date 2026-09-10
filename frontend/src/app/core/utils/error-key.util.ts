/**
 * Some server errors come back as a translation key in the response body's
 * `detail` field (see forum_service.py's _DM_FORBIDDEN_MESSAGE /
 * _INVALID_CURSOR_MESSAGE / InvalidTag handling) — any other detail (network
 * failure, an unrecognized key) falls back to a message of ours rather than
 * showing the raw backend value.
 *
 * Only *some*: since ABF-137 most of the backend raises through
 * `translate()`, which resolves the key against the request's Accept-Language
 * and puts the finished sentence in `detail`. There is nothing for this list
 * to recognise in those — the reporting errors included, which is why no
 * `reports.*` name appears below. What is left here is the older shape, where
 * the server names a key and the client renders it.
 */
export const KNOWN_ERROR_KEYS = [
  'errors.dm_forbidden',
  'errors.dm_restricted',
  'errors.invalid_cursor',
  'errors.internal_server_error',
];

/**
 * The translation key a screen should show for a failed request.
 *
 * `fallbackKey` is what to say when the server did not name a reason — pass
 * one whenever the screen can be more specific than "something went wrong"
 * ("the message was not sent", "older messages could not be loaded"). A
 * recognised server key always wins over it: the server knows *why*, and the
 * screen only knows *what* it was doing.
 */
export function errorKeyFrom(err: unknown, fallbackKey = 'errors.generic'): string {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' && KNOWN_ERROR_KEYS.includes(detail) ? detail : fallbackKey;
}
