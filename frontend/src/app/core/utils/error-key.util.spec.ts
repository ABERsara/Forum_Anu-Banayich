/**
 * Guards the pairing `errorKeyFrom` depends on and nothing else enforces.
 *
 * A server error key has to clear two separate hurdles to reach a reader: it
 * must be in `KNOWN_ERROR_KEYS` here, and it must exist in `he.json` and
 * `en.json`. Failing either is silent — an unlisted key degrades to
 * `errors.generic`, and a listed key with no translation renders as its own
 * dotted path. Neither shows up as a failing build, which is why the
 * combination is asserted rather than assumed.
 *
 * Written with ABF-122, the first ticket to add server error keys that the
 * screen showing them (ABF-123) lands in a different PR — the gap the guard
 * exists to close.
 */

import { TRANSLATIONS } from '../../../testing/transloco-testing';
import { errorKeyFrom } from './error-key.util';

/** Every key the API is known to send in `detail`. */
const SERVER_ERROR_KEYS = [
  'errors.dm_forbidden',
  'errors.invalid_cursor',
  'errors.internal_server_error',
  'errors.agent_domain_not_found',
  'errors.agent_conversation_not_found',
  'errors.agent_conversation_forbidden',
  'errors.agent_rate_limited',
  'errors.agent_unavailable',
];

/** `'errors.agent_unavailable'` → the string at that path, or undefined. */
function lookup(source: unknown, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], source);
}

describe('errorKeyFrom', () => {
  it.each(SERVER_ERROR_KEYS)('recognises %s instead of falling back', (key) => {
    expect(errorKeyFrom({ error: { detail: key } }, 'errors.generic')).toBe(key);
  });

  it.each(SERVER_ERROR_KEYS)('has a Hebrew and an English translation for %s', (key) => {
    expect(lookup(TRANSLATIONS.he, key), `${key} missing from he.json`).toBeTypeOf('string');
    expect(lookup(TRANSLATIONS.en, key), `${key} missing from en.json`).toBeTypeOf('string');
  });

  it('falls back for a detail the API did not name', () => {
    expect(errorKeyFrom({ error: { detail: 'errors.not_a_real_key' } })).toBe('errors.generic');
  });

  it('falls back when there is no detail at all', () => {
    expect(errorKeyFrom(new Error('network down'), 'messages.chat.send_failed')).toBe(
      'messages.chat.send_failed',
    );
  });
});
