/**
 * Locale service.
 *
 * Owns the app's active UI language (Hebrew / English), persists the
 * user's choice to localStorage, and keeps <html lang>/<html dir> in sync
 * with it. Delegates translation lookup/loading to Transloco — this
 * service only decides *which* language is active and applies the
 * RTL/LTR side effect on the document root.
 */

import { Injectable, computed, inject, signal } from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';

export type AppLang = 'he' | 'en';

const LANG_STORAGE_KEY = 'app_lang';
const DEFAULT_LANG: AppLang = 'he';

@Injectable({ providedIn: 'root' })
export class LocaleService {
  private readonly transloco = inject(TranslocoService);

  private readonly _lang = signal<AppLang>(this.readInitialLang());

  readonly lang = this._lang.asReadonly();
  readonly dir = computed(() => (this._lang() === 'he' ? 'rtl' : 'ltr'));

  constructor() {
    this.applyLang(this._lang(), { persist: false });
  }

  setLang(lang: AppLang): void {
    if (lang === this._lang()) return;
    this._lang.set(lang);
    this.applyLang(lang, { persist: true });
  }

  toggleLang(): void {
    this.setLang(this._lang() === 'he' ? 'en' : 'he');
  }

  private applyLang(lang: AppLang, opts: { persist: boolean }): void {
    this.transloco.setActiveLang(lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'he' ? 'rtl' : 'ltr';
    if (opts.persist) localStorage.setItem(LANG_STORAGE_KEY, lang);
  }

  private readInitialLang(): AppLang {
    const stored = localStorage.getItem(LANG_STORAGE_KEY);
    return stored === 'he' || stored === 'en' ? stored : DEFAULT_LANG;
  }
}
