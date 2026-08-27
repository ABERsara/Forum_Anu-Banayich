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
import { HttpErrorResponse } from '@angular/common/http';
import { RouterLink } from '@angular/router';

import { UserModerationCard } from '../../../core/models';
import {
  ACCOUNT_STATUS_LABELS,
  AccountStatus,
  SECTOR_LABELS,
  USER_TYPE_LABELS,
} from '../../../core/constants';
import { ReportService } from '../../../core/services/report.service';
import { ButtonComponent } from '../../../shared/components/button/button.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';
import {
  SuspendDialogComponent,
  SuspendDialogResult,
} from '../../../shared/components/suspend-dialog/suspend-dialog.component';

/** Shown wherever a user carries no group or sector yet. */
const NO_CELL = '—';

@Component({
  selector: 'app-moderator-user-card',
  standalone: true,
  imports: [
    DatePipe,
    RouterLink,
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

  readonly card = signal<UserModerationCard | null>(null);
  readonly isLoading = signal(false);
  readonly hasError = signal(false);

  readonly isSuspendDialogOpen = signal(false);
  readonly isSuspending = signal(false);
  readonly actionError = signal<string | null>(null);

  readonly fullName = computed(() => {
    const card = this.card();
    return card ? `${card.first_name} ${card.last_name}` : '';
  });

  /** The user's cell — the group and sector this moderator is responsible for. */
  readonly cellLabel = computed(() => {
    const card = this.card();
    if (!card?.user_type || !card.sector) {
      return NO_CELL;
    }
    return `${USER_TYPE_LABELS[card.user_type]} · ${SECTOR_LABELS[card.sector]}`;
  });

  readonly statusLabel = computed(() => {
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
    this.actionError.set(null);
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
      error: (err: HttpErrorResponse) => {
        this.actionError.set(this.messageFrom(err, 'אירעה שגיאה בהשעיית המשתמש. נסי שוב.'));
        this.isSuspendDialogOpen.set(false);
        this.isSuspending.set(false);
      },
    });
  }

  private messageFrom(err: HttpErrorResponse, fallback: string): string {
    const detail: unknown = err.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }
}
