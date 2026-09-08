/**
 * The three places a server error key has to be registered, and the guard
 * that catches the one everybody forgets.
 *
 * A backend that raises `detail: "errors.something"` is only half the job.
 * The key also has to be in KNOWN_ERROR_KEYS here, and in both translation
 * catalogues. Miss the allowlist and `errorKeyFrom()` quietly falls back to
 * "something went wrong" — no error, no failing test, just a screen that
 * stopped saying why. Miss a catalogue and Transloco renders the raw key.
 *
 * So this spec reads the backend's own source for the keys it raises and
 * checks all three registrations, rather than trusting a list kept by hand.
 */

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { KNOWN_ERROR_KEYS, errorKeyFrom } from './error-key.util';
import { TRANSLATIONS } from '../../../testing/transloco-testing';

/** Vitest runs from `frontend/`, so the repo root is one level up. */
const BACKEND_APP = join(process.cwd(), '..', 'backend', 'app');

/** Every .py file under backend/app, recursively. */
function pythonSources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === '__pycache__' ? [] : pythonSources(path);
    return entry.name.endsWith('.py') ? [path] : [];
  });
}

/** core/messages.py — the ABF-137 catalogue. Its keys are definitions. */
const CATALOGUE = join(BACKEND_APP, 'core', 'messages.py');

/**
 * The `errors.*` keys the backend hands to the *client* to resolve.
 *
 * Two shapes reach `detail`, and only one of them is a key. `translate("…")`
 * resolves against the request's Accept-Language and puts a finished sentence
 * there — nothing for the client to look up, and nothing this list should
 * carry. A bare literal, the shape forum_service.py still raises the DM errors
 * in, arrives as the key itself. So translate()'s arguments are blanked before
 * the scan, and the catalogue that *defines* every key is skipped outright —
 * otherwise every message in the app would read as one the client resolves.
 *
 * A string literal is enough to find what remains: the backend writes those as
 * plain literals, either inline in an HTTPException or as a module constant,
 * and both forms are the text this matches.
 */
function backendErrorKeys(): Set<string> {
  const keys = new Set<string>();
  for (const file of pythonSources(BACKEND_APP)) {
    if (file === CATALOGUE) continue;
    const source = readFileSync(file, 'utf8').replaceAll(/translate\(\s*"[^"]*"/g, 'translate(');
    for (const match of source.matchAll(/"(errors\.[a-z0-9_]+)"/g)) keys.add(match[1]);
  }
  return keys;
}

/** `{a: {b: 'x'}}` → `{'a.b': 'x'}`, the shape Transloco looks keys up in. */
function flatten(source: unknown, prefix = ''): Record<string, string> {
  const flat: Record<string, string> = {};
  for (const [key, value] of Object.entries(source as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') flat[path] = value;
    else Object.assign(flat, flatten(value, path));
  }
  return flat;
}

const HE = flatten(TRANSLATIONS.he);
const EN = flatten(TRANSLATIONS.en);

describe('errorKeyFrom', () => {
  it('returns a key the server named, when it is one we know', () => {
    const err = { error: { detail: 'errors.dm_forbidden' } };

    expect(errorKeyFrom(err)).toBe('errors.dm_forbidden');
  });

  it('prefers the server key over the screen fallback', () => {
    const err = { error: { detail: 'errors.invalid_cursor' } };

    expect(errorKeyFrom(err, 'messages.chat.send_failed')).toBe('errors.invalid_cursor');
  });

  it('falls back rather than showing an unrecognised server value', () => {
    const err = { error: { detail: 'Traceback (most recent call last): ...' } };

    expect(errorKeyFrom(err, 'messages.chat.send_failed')).toBe('messages.chat.send_failed');
  });

  it('falls back on a failure with no detail at all', () => {
    expect(errorKeyFrom(new Error('offline'))).toBe('errors.generic');
  });
});

describe('server error keys', () => {
  it.each([
    ['he', HE],
    ['en', EN],
  ])('are all translated in %s.json', (lang, catalogue) => {
    const missing = KNOWN_ERROR_KEYS.filter((key) => !(key in catalogue));

    expect(missing, `allowlisted keys with no ${lang}.json entry`).toEqual([]);
  });

  /**
   * The registration that fails silently. A key the backend raises but this
   * list does not carry is not an error anywhere — the screen just stops
   * saying why it failed.
   */
  it('are all allowlisted, so a reason the server gave is not thrown away', () => {
    const unlisted = [...backendErrorKeys()].filter((key) => !KNOWN_ERROR_KEYS.includes(key));

    expect(unlisted, 'keys the backend raises that errorKeyFrom() would discard').toEqual([]);
  });

  it('carry no allowlisted key the backend never raises', () => {
    const raised = backendErrorKeys();
    const stale = KNOWN_ERROR_KEYS.filter((key) => !raised.has(key));

    expect(stale, 'allowlisted keys no backend path returns').toEqual([]);
  });
});
