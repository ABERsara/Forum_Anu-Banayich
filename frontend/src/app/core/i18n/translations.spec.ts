/**
 * Guards `he.json` and `en.json` against drifting apart.
 *
 * `core/constants/index.spec.ts` (ABF-127) already guards the `constants.*`
 * namespace, because the ten shared label maps had to be complete in both
 * languages from the day they stopped holding Hebrew. This spec widens that to
 * the whole file, which the seven migration tickets each need anyway: their
 * acceptance criteria say "no key missing in either language", and a key that
 * exists in Hebrew alone leaks a raw `home.forum.title` onto an English screen
 * long after the commit that dropped it.
 *
 * The value of a key is deliberately not checked. "אחר" and "Other" are both
 * legitimate; an English entry left as Hebrew is a translation review, not a
 * build failure.
 */

import { TRANSLATIONS } from '../../../testing/transloco-testing';

/** `{a: {b: 'x'}}` → `{'a.b': 'x'}`, the shape Transloco looks keys up in. */
function flatten(source: unknown, prefix = ''): Record<string, string> {
  const flat: Record<string, string> = {};
  for (const [key, value] of Object.entries(source as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      flat[path] = value;
    } else {
      Object.assign(flat, flatten(value, path));
    }
  }
  return flat;
}

const HE = flatten(TRANSLATIONS.he);
const EN = flatten(TRANSLATIONS.en);

describe('translation files', () => {
  it('hold the same keys in both languages', () => {
    const missingFromEn = Object.keys(HE).filter((key) => !(key in EN));
    const missingFromHe = Object.keys(EN).filter((key) => !(key in HE));

    expect(missingFromEn, 'keys in he.json with no en.json entry').toEqual([]);
    expect(missingFromHe, 'keys in en.json with no he.json entry').toEqual([]);
  });

  it.each([
    ['he', HE],
    ['en', EN],
  ])('leave no key blank in %s.json', (lang, translations) => {
    const blank = Object.entries(translations)
      .filter(([, value]) => value.trim() === '')
      .map(([key]) => key);

    expect(blank, `keys with an empty ${lang} translation`).toEqual([]);
  });

  /**
   * A parameter renamed on one side only resolves to nothing on that side —
   * "Hello, " with the name silently dropped. Cheap to catch here, invisible
   * in review.
   */
  it('interpolate the same parameters in both languages', () => {
    const params = (value: string) =>
      [...value.matchAll(/\{\{\s*([\w.]+)\s*\}\}/g)].map((match) => match[1]).sort();

    const mismatched = Object.keys(HE)
      .filter((key) => key in EN)
      .filter((key) => params(HE[key]).join() !== params(EN[key]).join());

    expect(mismatched, 'keys whose he/en text interpolate different names').toEqual([]);
  });
});
