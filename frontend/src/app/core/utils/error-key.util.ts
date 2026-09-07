/**
 * Server errors come back as a translation key in the response body's
 * `detail` field (see forum_service.py's _DM_FORBIDDEN_MESSAGE /
 * _INVALID_CURSOR_MESSAGE / InvalidTag handling) — any other detail (network
 * failure, an unrecognized key) falls back to a message of ours rather than
 * showing the raw backend value.
 */
const KNOWN_ERROR_KEYS = [
  'errors.dm_forbidden',
  'errors.invalid_cursor',
  'errors.internal_server_error',
  // AI agent (ABF-122). Registered by the ticket that made the API send these,
  // not by the screen that will show them (ABF-123): a key missing from this
  // list fails nowhere — it silently becomes `errors.generic`, so "this agent
  // is not available" and "you have reached today's limit" would both read
  // "something went wrong", with no failing test to say why.
  'errors.agent_domain_not_found',
  'errors.agent_conversation_not_found',
  'errors.agent_conversation_forbidden',
  'errors.agent_rate_limited',
  'errors.agent_unavailable',
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
