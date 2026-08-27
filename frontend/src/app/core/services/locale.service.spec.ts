import { TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { vi } from 'vitest';

import { LocaleService } from './locale.service';

describe('LocaleService', () => {
  let translocoMock: { setActiveLang: ReturnType<typeof vi.fn> };

  const buildService = (): LocaleService => TestBed.inject(LocaleService);

  beforeEach(() => {
    localStorage.clear();
    document.documentElement.lang = '';
    document.documentElement.dir = '';

    translocoMock = { setActiveLang: vi.fn() };

    TestBed.configureTestingModule({
      providers: [{ provide: TranslocoService, useValue: translocoMock }],
    });
  });

  afterEach(() => {
    localStorage.clear();
    document.documentElement.lang = '';
    document.documentElement.dir = '';
  });

  it('defaults to Hebrew/RTL when nothing is stored', () => {
    const service = buildService();

    expect(service.lang()).toBe('he');
    expect(service.dir()).toBe('rtl');
    expect(document.documentElement.lang).toBe('he');
    expect(document.documentElement.dir).toBe('rtl');
  });

  it('reads a valid stored language on init', () => {
    localStorage.setItem('app_lang', 'en');

    const service = buildService();

    expect(service.lang()).toBe('en');
    expect(service.dir()).toBe('ltr');
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dir).toBe('ltr');
  });

  it('falls back to the default language when the stored value is invalid', () => {
    localStorage.setItem('app_lang', 'fr');

    const service = buildService();

    expect(service.lang()).toBe('he');
  });

  it('setLang updates the signal, document attributes, localStorage, and Transloco', () => {
    const service = buildService();

    service.setLang('en');

    expect(service.lang()).toBe('en');
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dir).toBe('ltr');
    expect(localStorage.getItem('app_lang')).toBe('en');
    expect(translocoMock.setActiveLang).toHaveBeenCalledWith('en');
  });

  it('setLang is a no-op when the language is already active', () => {
    const service = buildService();
    translocoMock.setActiveLang.mockClear();

    service.setLang('he');

    expect(translocoMock.setActiveLang).not.toHaveBeenCalled();
  });

  it('toggleLang flips between he and en', () => {
    const service = buildService();

    service.toggleLang();
    expect(service.lang()).toBe('en');

    service.toggleLang();
    expect(service.lang()).toBe('he');
  });
});
