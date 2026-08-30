/**
 * Resolves the shared label keys from `core/constants` into display text.
 *
 * **Templates should not use this** — they have the `transloco` pipe, which is
 * shorter and refreshes itself:
 *
 * ```html
 * {{ sectorLabels[user.sector] | transloco }}
 * ```
 *
 * This service is for the handful of places a pipe cannot reach: where the
 * string is assembled in TypeScript out of several labels, or where a method
 * returns a label in one branch and something that is not a key at all — a
 * person's name, say — in another.
 */

import { Injectable, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { TranslocoService } from '@jsverse/transloco';

import { LabelKey } from '../constants';

@Injectable({ providedIn: 'root' })
export class LabelService {
  private readonly transloco = inject(TranslocoService);

  /**
   * The active language, as a signal.
   *
   * `label()` reads it before every lookup, so a template that calls `label()`
   * takes a reactive dependency on the language and re-renders on a switch.
   * A bare `transloco.translate()` would return the right text once and then
   * go stale — this read is what the `transloco` pipe's own subscription does
   * for templates.
   */
  private readonly activeLang = toSignal(this.transloco.langChanges$);

  /** The text for one label key. An empty key stays empty, as Transloco does. */
  label(key: LabelKey): string {
    this.activeLang();
    return this.transloco.translate(key);
  }
}
