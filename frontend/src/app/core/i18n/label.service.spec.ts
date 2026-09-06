import { computed } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';

import { LabelService } from './label.service';
import { Sector, SECTOR_LABELS } from '../constants';
import { translocoTesting } from '../../../testing/transloco-testing';

describe('LabelService', () => {
  let service: LabelService;
  let transloco: TranslocoService;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [translocoTesting()] });
    service = TestBed.inject(LabelService);
    transloco = TestBed.inject(TranslocoService);
  });

  it('resolves a label key in the active language', () => {
    expect(service.label(SECTOR_LABELS[Sector.HASIDIC])).toBe('חסידי');

    transloco.setActiveLang('en');

    expect(service.label(SECTOR_LABELS[Sector.HASIDIC])).toBe('Hasidic');
  });

  it('passes an empty key through, so an absent label renders as nothing', () => {
    expect(service.label('')).toBe('');
  });

  /**
   * The reason the service exists rather than callers reaching for
   * `translate()`: a reader that memoises on the key alone would still be
   * holding "ליטאי" after the switch.
   */
  it('invalidates a reader that memoised on it when the language changes', () => {
    const label = computed(() => service.label(SECTOR_LABELS[Sector.LITVISH]));
    expect(label()).toBe('ליטאי');

    transloco.setActiveLang('en');

    expect(label()).toBe('Litvish');
  });
});
