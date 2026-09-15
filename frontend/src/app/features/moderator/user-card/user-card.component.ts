/**
 * Moderator's user card (SPEC §7.3, "כרטיס משתמש").
 *
 * One user's moderation history — how often they were reported and how those
 * reports were decided, how many of the reports they themselves filed turned
 * out to be false — plus the manual suspension that history may justify.
 *
 * Reached from a row of the reports queue, and scoped server-side: a
 * moderator only ever opens the card of a user in a cell they oversee.
 *
 * The copy lives under `moderator.user_card.*` in he.json/en.json, alongside
 * the reports board ABF-134 migrated — a screen added to a module that has
 * already moved does not bring hardcoded Hebrew back in (CONTRIBUTING §6).
 *
 * Important:
 *   - No contact details. The moderator sees counts and a cell, not the
 *     person's email, phone or ID number.
 *   - Suspending is a two-step action: the button opens a dialog that will
 *     not submit without a duration and a written reason.
 */

import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { UserModerationCard } from '../../../core/models';
import {
  ACCOUNT_STATUS_LABELS,
  AccountStatus,
  LabelKey,
  SECTOR_LABELS,
  USER_TYPE_LABELS,
} from '../../../core/constants';
import { LabelService } from '../../../core/i18n/label.service';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { ReportService } from '../../../core/services/report.service';
import { ButtonComponent } from '../../../shared/components/button/button.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';
import {
  SuspendDialogComponent,
  SuspendDialogResult,
} from '../../../shared/components/suspend-dialog/suspend-dialog.component';

/**
 * Shown wherever a user carries no group or sector yet.
 *
 * An em dash is a glyph, not copy — it reads the same in both languages and
 * is Bidi-neutral, so it stays out of the translation files (ABF-132).
 */
const NO_CELL = '—';

@Component({
  selector: 'app-moderator-user-card',
  standalone: true,
  imports: [
    DatePipe,
    RouterLink,
    TranslocoPipe,
    ButtonComponent,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
    SuspendDialogComponent,
  ],
  templateUrl: './user-card.component.html',
  styleUrl: './user-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ModeratorUserCardComponent implements OnInit {
  /** Bound from the :userId route parameter (withComponentInputBinding). */
  readonly userId = input.required<string>();

  private readonly reportService = inject(ReportService);
  private readonly labels = inject(LabelService);

  readonly card = signal<UserModerationCard | null>(null);
  readonly isLoading = signal(false);
  readonly hasError = signal(false);

  readonly isSuspendDialogOpen = signal(false);
  readonly isSuspending = signal(false);
  /** Held as a key or a server sentence, never as translated text (ABF-132). */
  readonly actionError = signal<ScreenError>(NO_ERROR);

  readonly fullName = computed(() => {
    const card = this.card();
    return card ? `${card.first_name} ${card.last_name}` : '';
  });

  /**
   * The user's cell — the group and sector this moderator is responsible for.
   *
   * Two shared labels joined into one string, which is the case the pipe
   * cannot reach: `LabelService.label()` reads the active language, so the
   * line still follows a language switch (CONTRIBUTING §6).
   */
  readonly cellLabel = computed(() => {
    const card = this.card();
    if (!card?.user_type || !card.sector) {
      return NO_CELL;
    }
    return `${this.labels.label(USER_TYPE_LABELS[card.user_type])} · ${this.labels.label(
      SECTOR_LABELS[card.sector],
    )}`;
  });

  /** A shared label *key* — the template pipes it (ABF-127). */
  readonly statusLabelKey = computed<LabelKey>(() => {
    const card = this.card();
    return card ? ACCOUNT_STATUS_LABELS[card.account_status] : '';
  });

  /**
   * Only an active account can be suspended — the server rejects anything
   * else, so the button is not offered for one.
   */
  readonly canSuspend = computed(() => this.card()?.account_status === AccountStatus.ACTIVE);

  ngOnInit(): void {
    this.loadCard();
  }

  private loadCard(): void {
    this.isLoading.set(true);
    this.hasError.set(false);
    this.reportService.getUserCard(this.userId()).subscribe({
      next: (card) => {
        this.card.set(card);
        this.isLoading.set(false);
      },
      error: () => {
        this.hasError.set(true);
        this.isLoading.set(false);
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Manual suspension
  // ---------------------------------------------------------------------------

  openSuspendDialog(): void {
    this.actionError.set(NO_ERROR);
    this.isSuspendDialogOpen.set(true);
  }

  cancelSuspend(): void {
    this.isSuspendDialogOpen.set(false);
  }

  confirmSuspend(result: SuspendDialogResult): void {
    this.isSuspending.set(true);
    this.reportService.suspendUser(this.userId(), result.hours, result.reason).subscribe({
      // The endpoint answers with the card as it now stands, so the counts
      // and the new suspension arrive together — no second request.
      next: (card) => {
        this.card.set(card);
        this.isSuspendDialogOpen.set(false);
        this.isSuspending.set(false);
      },
      error: (err: unknown) => {
        this.actionError.set(screenErrorFrom(err, 'moderator.errors.suspend_failed'));
        this.isSuspendDialogOpen.set(false);
        this.isSuspending.set(false);
      },
    });
  }
}
