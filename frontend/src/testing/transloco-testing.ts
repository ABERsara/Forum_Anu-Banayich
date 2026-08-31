/**
 * Transloco for specs, wired to the app's real translation files.
 *
 * Specs that render a translated label import this rather than stubbing the
 * text, so an assertion on "אלמנה" is checking the same `he.json` the browser
 * loads. A key that goes missing from a translation file therefore fails the
 * spec that renders it, not only the guard in `core/constants/index.spec.ts`.
 *
 * ```ts
 * TestBed.configureTestingModule({
 *   imports: [MyComponent, translocoTesting()],
 * });
 * ```
 *
 * Pass `{ defaultLang: 'en' }` to assert the English side of a label.
 */

import { TranslocoTestingModule, TranslocoTestingOptions } from '@jsverse/transloco';

import en from '../../public/i18n/en.json';
import he from '../../public/i18n/he.json';

/** The translation files themselves, for specs that assert against them. */
export const TRANSLATIONS = { he, en };

export function translocoTesting(options: { defaultLang?: 'he' | 'en' } = {}) {
  const config: TranslocoTestingOptions = {
    langs: TRANSLATIONS,
    translocoConfig: {
      availableLangs: ['he', 'en'],
      defaultLang: options.defaultLang ?? 'he',
      reRenderOnLangChange: true,
    },
    preloadLangs: true,
  };

  return TranslocoTestingModule.forRoot(config);
}
