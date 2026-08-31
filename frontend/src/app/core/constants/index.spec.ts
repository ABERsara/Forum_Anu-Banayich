/**
 * Guards the shared label maps against the two ways a key can rot: a key with
 * no entry behind it in one of the languages, and an entry no map points at
 * any more.
 *
 * These ten maps are imported by a dozen feature modules and will be migrated
 * one module at a time, so the drift this catches would otherwise surface as a
 * raw `constants.sector.hasidic` on someone's screen, in one language only,
 * long after the commit that caused it.
 */

import {
  ACCOUNT_STATUS_LABELS,
  DOCUMENT_TYPE_LABELS,
  GROUP_VISIBILITY_LABELS,
  LabelKey,
  POST_STATUS_LABELS,
  PROFESSIONAL_DOMAIN_LABELS,
  QUERY_STATUS_LABELS,
  REPORT_REASON_LABELS,
  SECTOR_LABELS,
  SECTOR_VISIBILITY_LABELS,
  USER_TYPE_LABELS,
} from './index';
import { TRANSLATIONS } from '../../../testing/transloco-testing';

/** The ten maps this ticket moved onto translation keys, by their export name. */
const LABEL_MAPS: Record<string, Record<string, LabelKey>> = {
  ACCOUNT_STATUS_LABELS,
  DOCUMENT_TYPE_LABELS,
  GROUP_VISIBILITY_LABELS,
  POST_STATUS_LABELS,
  PROFESSIONAL_DOMAIN_LABELS,
  QUERY_STATUS_LABELS,
  REPORT_REASON_LABELS,
  SECTOR_LABELS,
  SECTOR_VISIBILITY_LABELS,
  USER_TYPE_LABELS,
};

/** Every key any of the maps points at, deduplicated. */
const USED_KEYS = new Set(Object.values(LABEL_MAPS).flatMap((map) => Object.values(map)));

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

describe('shared label maps', () => {
  it('hold translation keys, never display text', () => {
    for (const [name, map] of Object.entries(LABEL_MAPS)) {
      for (const [value, key] of Object.entries(map)) {
        expect(`${name}[${value}] = ${key}`).toMatch(/= constants\.[a-z_]+\.[a-z_]+$/);
      }
    }
  });

  it.each([
    ['he', HE],
    ['en', EN],
  ])('resolve to a translation in %s.json', (lang, translations) => {
    const missing = [...USED_KEYS].filter((key) => !translations[key]);

    expect(missing, `keys with no ${lang} translation`).toEqual([]);
  });

  it('carry the same constants keys in both languages', () => {
    const constantsOf = (t: Record<string, string>) =>
      Object.keys(t)
        .filter((key) => key.startsWith('constants.'))
        .sort();

    expect(constantsOf(HE)).toEqual(constantsOf(EN));
  });

  it('leave no constants translation orphaned', () => {
    const orphaned = Object.keys(HE)
      .filter((key) => key.startsWith('constants.'))
      .filter((key) => !USED_KEYS.has(key));

    expect(orphaned, 'translations no label map points at').toEqual([]);
  });
});
