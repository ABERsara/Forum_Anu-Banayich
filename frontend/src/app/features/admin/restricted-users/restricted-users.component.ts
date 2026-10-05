import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { TranslocoPipe } from '@jsverse/transloco';

import { UserAdminView } from '../../../core/models';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { AdminService } from '../../../core/services/admin.service';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';

@Component({
  selector: 'app-restricted-users',
  standalone: true,
  imports: [
    RouterLink,
    TranslocoPipe,
    LoadingSpinnerComponent,
    ErrorDisplayComponent,
    ConfirmDialogComponent,
  ],
  templateUrl: './restricted-users.component.html',
  styleUrl: './restricted-users.component.scss',
})
export class RestrictedUsersComponent implements OnInit {
  private readonly adminService = inject(AdminService);

  users = signal<UserAdminView[]>([]);
  isLoading = signal(false);
  hasError = signal(false);
  /** What went wrong lifting a restriction, as a key of ours or a sentence the API sent. */
  actionError = signal<ScreenError>(NO_ERROR);
  liftingId = signal<string | null>(null);

  ngOnInit(): void {
    this.isLoading.set(true);
    this.hasError.set(false);
    this.adminService.getRestrictedUsers().subscribe({
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

  lift(userId: string): void {
    this.actionError.set(NO_ERROR);
    this.liftingId.set(userId);
  }

  cancelLift(): void {
    this.liftingId.set(null);
  }

  confirmLift(): void {
    const userId = this.liftingId();
    if (!userId) {
      return;
    }
    this.adminService.liftRestriction(userId).subscribe({
      next: () => {
        this.users.set(this.users().filter((u) => u.id !== userId));
        this.liftingId.set(null);
      },
      error: (err: HttpErrorResponse) => {
        this.liftingId.set(null);
        this.actionError.set(screenErrorFrom(err, 'admin.errors.lift_restriction_failed'));
      },
    });
  }
}
