/**
 * User profile / account settings screen.
 *
 * Also hosts SPEC §9.4/§9.5's self-service data controls (ABF-117): a short
 * explanation of the private-message retention policy plus an export
 * action (USER role only — SPEC §3.2's permission table grants export to
 * that role alone), and account deletion (every role, per the same table).
 *
 * The screen owns no direction of its own (ABF-136): `LocaleService` sets
 * `<html dir>` from the active language and the page inherits it.
 */

import { Component, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { TranslocoPipe } from '@jsverse/transloco';

import {
  ACCOUNT_STATUS_LABELS,
  SECTOR_LABELS,
  UserRole,
  USER_TYPE_LABELS,
} from '../../core/constants';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../core/i18n/screen-error';
import { DirectMessageExportResult } from '../../core/models';
import { AuthService } from '../../core/services/auth.service';
import { ConfirmDialogComponent } from '../../shared/components/confirm-dialog/confirm-dialog.component';
import { ErrorDisplayComponent } from '../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [TranslocoPipe, ConfirmDialogComponent, ErrorDisplayComponent, LoadingSpinnerComponent],
  templateUrl: './profile.component.html',
  styleUrl: './profile.component.scss',
})
export class ProfileComponent {
  readonly auth = inject(AuthService);
  readonly userTypeLabels = USER_TYPE_LABELS;
  readonly sectorLabels = SECTOR_LABELS;
  readonly statusLabels = ACCOUNT_STATUS_LABELS;
  readonly userRole = UserRole;

  isExporting = signal(false);
  exportError = signal<ScreenError>(NO_ERROR);
  exportSuccess = signal(false);

  showDeleteConfirm = signal(false);
  isDeleting = signal(false);
  deleteError = signal<ScreenError>(NO_ERROR);

  exportMessages(): void {
    this.isExporting.set(true);
    this.exportError.set(NO_ERROR);
    this.exportSuccess.set(false);
    this.auth.exportMyMessages().subscribe({
      next: (result) => {
        this.downloadExport(result);
        this.isExporting.set(false);
        this.exportSuccess.set(true);
      },
      error: (err: HttpErrorResponse) => {
        this.exportError.set(screenErrorFrom(err, 'profile.errors.export_failed'));
        this.isExporting.set(false);
      },
    });
  }

  onDeleteAccountClick(): void {
    this.deleteError.set(NO_ERROR);
    this.showDeleteConfirm.set(true);
  }

  onDeleteAccountCancelled(): void {
    this.showDeleteConfirm.set(false);
  }

  onDeleteAccountConfirmed(): void {
    this.showDeleteConfirm.set(false);
    this.isDeleting.set(true);
    this.deleteError.set(NO_ERROR);
    this.auth.deleteMyAccount().subscribe({
      next: () => this.auth.logout(),
      error: (err: HttpErrorResponse) => {
        this.deleteError.set(screenErrorFrom(err, 'profile.errors.delete_account_failed'));
        this.isDeleting.set(false);
      },
    });
  }

  /**
   * Hands the export to the browser as a downloaded file rather than
   * rendering it — this is a personal-data export a member takes away and
   * keeps, not a screen of content.
   */
  private downloadExport(result: DirectMessageExportResult): void {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `my-messages-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }
}
