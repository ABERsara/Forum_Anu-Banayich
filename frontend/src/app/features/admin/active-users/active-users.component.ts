import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { TranslocoPipe } from '@jsverse/transloco';

import { UserAdminView } from '../../../core/models';
import { SECTOR_LABELS, USER_TYPE_LABELS } from '../../../core/constants';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { AdminService } from '../../../core/services/admin.service';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import {
  SuspendDialogComponent,
  SuspendDialogResult,
} from '../../../shared/components/suspend-dialog/suspend-dialog.component';

@Component({
  selector: 'app-active-users',
  standalone: true,
  imports: [
    RouterLink,
    TranslocoPipe,
    LoadingSpinnerComponent,
    ErrorDisplayComponent,
    SuspendDialogComponent,
  ],
  templateUrl: './active-users.component.html',
  styleUrl: './active-users.component.scss',
})
export class ActiveUsersComponent implements OnInit {
  private readonly adminService = inject(AdminService);

  users = signal<UserAdminView[]>([]);
  isLoading = signal(false);
  hasError = signal(false);
  /** What went wrong on suspend, as a key of ours or a sentence the API sent. */
  actionError = signal<ScreenError>(NO_ERROR);
  suspendingId = signal<string | null>(null);
  readonly userTypeLabels = USER_TYPE_LABELS;
  readonly sectorLabels = SECTOR_LABELS;

  ngOnInit(): void {
    this.isLoading.set(true);
    this.hasError.set(false);
    this.adminService.getActiveUsers().subscribe({
      next: (result) => {
        this.users.set(result);
        this.isLoading.set(false);
      },
      error: () => {
        this.hasError.set(true);
        this.isLoading.set(false);
      },
    });
  }

  suspend(userId: string): void {
    this.actionError.set(NO_ERROR);
    this.suspendingId.set(userId);
  }

  cancelSuspend(): void {
    this.suspendingId.set(null);
  }

  confirmSuspend(result: SuspendDialogResult): void {
    const userId = this.suspendingId();
    if (!userId) {
      return;
    }
    this.adminService.suspendUser(userId, result.hours, result.reason).subscribe({
      next: () => {
        this.users.set(this.users().filter((u) => u.id !== userId));
        this.suspendingId.set(null);
      },
      error: (err: HttpErrorResponse) =>
        this.actionError.set(screenErrorFrom(err, 'admin.errors.suspend_failed')),
    });
  }
}
