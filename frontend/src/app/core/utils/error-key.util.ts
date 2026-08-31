/**
 * Server errors come back as a translation key in the response body's
 * `detail` field (see forum_service.py's _DM_FORBIDDEN_MESSAGE / InvalidTag
 * handling) — any other detail (network failure, an unrecognized key) falls
 * back to a generic message rather than showing the raw backend value.
 */
const KNOWN_ERROR_KEYS = ['errors.dm_forbidden', 'errors.internal_server_error'];

export function errorKeyFrom(err: unknown): string {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' && KNOWN_ERROR_KEYS.includes(detail)
    ? detail
    : 'errors.generic';
}
