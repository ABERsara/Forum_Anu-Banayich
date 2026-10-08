import { computed } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';

import { auditActionLabel, auditOccurredAt } from './audit-log.util';
import { AuditAction } from '../../../core/constants';
import { LabelService } from '../../../core/i18n/label.service';
import { translocoTesting } from '../../../../testing/transloco-testing';

describe('audit-log.util', () => {
  describe('auditActionLabel', () => {
    let labels: LabelService;
    let transloco: TranslocoService;

    beforeEach(() => {
      TestBed.configureTestingModule({ imports: [translocoTesting()] });
      labels = TestBed.inject(LabelService);
      transloco = TestBed.inject(TranslocoService);
    });

    it('names a known action in the active language', () => {
      expect(auditActionLabel({ action_type: AuditAction.USER_SUSPENDED }, labels)).toBe(
        'השעיית משתמש/ת',
      );

      transloco.setActiveLang('en');

      expect(auditActionLabel({ action_type: AuditAction.USER_SUSPENDED }, labels)).toBe(
        'User suspended',
      );
    });

    it('falls back to the raw wire value for an action this build has no label for', () => {
      const unknown = { action_type: 'some_new_action' as AuditAction };

      expect(auditActionLabel(unknown, labels)).toBe('some_new_action');
    });

    /** What lets a template that calls it re-render on a language switch. */
    it('invalidates a reader that memoised on it when the language changes', () => {
      const label = computed(() =>
        auditActionLabel({ action_type: AuditAction.USER_SUSPENDED }, labels),
      );
      expect(label()).toBe('השעיית משתמש/ת');

      transloco.setActiveLang('en');

      expect(label()).toBe('User suspended');
    });
  });

  describe('auditOccurredAt', () => {
    it('reads the naive timestamp the API sends as UTC', () => {
      const instant = auditOccurredAt({ timestamp: '2026-09-01T12:00:00' });

      expect(instant).toBe('2026-09-01T12:00:00Z');
      expect(new Date(instant).toISOString()).toBe('2026-09-01T12:00:00.000Z');
    });

    it('leaves a timestamp that already carries an offset alone', () => {
      expect(auditOccurredAt({ timestamp: '2026-09-01T12:00:00Z' })).toBe('2026-09-01T12:00:00Z');
      expect(auditOccurredAt({ timestamp: '2026-09-01T15:00:00+03:00' })).toBe(
        '2026-09-01T15:00:00+03:00',
      );
    });
  });
});
