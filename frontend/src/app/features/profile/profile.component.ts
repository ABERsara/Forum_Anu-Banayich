/**
 * User profile / account settings screen.
 *
 * Also hosts SPEC §9.4/§9.5's self-service data controls (ABF-117): a short
 * explanation of the private-message retention policy plus an export
 * action (USER role only — SPEC §3.2's permission table grants export to
 * that role alone), and account deletion (every role, per the same table).
 *
 * ABF-165 adds the one profile field a user edits themselves: the alert
 * address, where the platform sends this account its alerts (every role).
 * The login address, name, group and sector stay read-only here: the first
 * needs the OTP flow, the rest are admin decisions.
 *
 * The screen owns no direction of its own (ABF-136): `LocaleService` sets
 * `<html dir>` from the active language and the page inherits it.
 */

import {
  Component,
  DestroyRef,
  ElementRef,
  Injector,
  ViewChild,
  afterNextRender,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { TranslocoPipe } from '@jsverse/transloco';

import {
  ACCOUNT_STATUS_LABELS,
  SECTOR_LABELS,
  UserRole,
  USER_TYPE_LABELS,
} from '../../core/constants';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../core/i18n/screen-error';
import { DirectMessageExportResult } from '../../core/models';
import { AccountService } from '../../core/services/account.service';
import { AuthService } from '../../core/services/auth.service';
import { ConfirmDialogComponent } from '../../shared/components/confirm-dialog/confirm-dialog.component';
import { ErrorDisplayComponent } from '../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    TranslocoPipe,
    ConfirmDialogComponent,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
  templateUrl: './profile.component.html',
  styleUrl: './profile.component.scss',
})
export class ProfileComponent {
  readonly auth = inject(AuthService);
  private readonly account = inject(AccountService);
  private readonly injector = inject(Injector);
  private readonly destroyRef = inject(DestroyRef);
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

  readonly alertEmailForm = new FormGroup({
    /** Blank means "no separate alert address": alerts go to the login address. */
    alert_email: new FormControl('', { nonNullable: true, validators: [Validators.email] }),
  });
  readonly alertEmail = this.alertEmailForm.controls.alert_email;
  isEditingAlertEmail = signal(false);
  isSavingAlertEmail = signal(false);
  alertEmailError = signal<ScreenError>(NO_ERROR);
  alertEmailSaved = signal(false);

  @ViewChild('alertEmailInput') private alertEmailInput?: ElementRef<HTMLInputElement>;
  @ViewChild('alertEmailEditButton') private alertEmailEditButton?: ElementRef<HTMLButtonElement>;

  /** Opens the field on the address currently stored. */
  editAlertEmail(): void {
    this.alertEmail.reset(this.storedAlertEmail());
    this.alertEmailError.set(NO_ERROR);
    this.alertEmailSaved.set(false);
    this.isEditingAlertEmail.set(true);
    this.focusAfterRender(() => this.alertEmailInput);
  }

  /** Puts back the stored address and sends nothing. */
  cancelAlertEmailEdit(): void {
    this.alertEmail.reset(this.storedAlertEmail());
    this.alertEmailError.set(NO_ERROR);
    this.isEditingAlertEmail.set(false);
    this.focusAfterRender(() => this.alertEmailEditButton);
  }

  saveAlertEmail(): void {
    // Judge the value that is about to be sent: a pasted "  a@b.co  " is a
    // valid address once trimmed, and Validators.email would reject it before.
    const value = this.alertEmail.value.trim();
    this.alertEmail.setValue(value);
    this.alertEmail.markAsTouched();
    if (this.alertEmail.invalid) return;

    this.isSavingAlertEmail.set(true);
    this.alertEmailError.set(NO_ERROR);
    this.alertEmailSaved.set(false);
    this.alertEmail.disable();
    // A cleared field is sent as null, not "": the API clears the address on
    // null and rejects an empty string as an invalid one.
    this.account
      .updateMyProfile({ alert_email: value || null })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (user) => {
          this.auth.setCurrentUser(user);
          this.alertEmail.enable();
          this.isSavingAlertEmail.set(false);
          this.isEditingAlertEmail.set(false);
          this.alertEmailSaved.set(true);
          this.focusAfterRender(() => this.alertEmailEditButton);
        },
        error: (err: HttpErrorResponse) => {
          // A 422 carries Pydantic's English field errors, not a sentence for the
          // reader. Validators.email accepts a few shapes the API does not
          // ("a@b", with no dot in the domain), so say what is wrong with it.
          const fallbackKey =
            err.status === 422
              ? 'profile.alert_email.email_error'
              : 'profile.errors.alert_email_save_failed';
          this.alertEmailError.set(screenErrorFrom(err, fallbackKey));
          this.alertEmail.enable();
          this.isSavingAlertEmail.set(false);
        },
      });
  }

  exportMessages(): void {
    this.isExporting.set(true);
    this.exportError.set(NO_ERROR);
    this.exportSuccess.set(false);
    this.account
      .exportMyMessages()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
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
    // Not takeUntilDestroyed, unlike the two calls above: unsubscribing aborts
    // the request, and the server may already have deleted the account. The
    // logout then never runs, and this tab keeps a token that every endpoint
    // answers with 403 (a 401 is what authInterceptor would log out on).
    this.account.deleteMyAccount().subscribe({
      next: () => this.auth.logout(),
      error: (err: HttpErrorResponse) => {
        this.deleteError.set(screenErrorFrom(err, 'profile.errors.delete_account_failed'));
        this.isDeleting.set(false);
      },
    });
  }

  private storedAlertEmail(): string {
    return this.auth.currentUser()?.alert_email ?? '';
  }

  /**
   * The edit and the read-only view swap places, so the element that had focus
   * leaves the page with them. Without this, keyboard and screen-reader users
   * land back at the top of the document.
   */
  private focusAfterRender(target: () => ElementRef<HTMLElement> | undefined): void {
    afterNextRender(() => target()?.nativeElement.focus(), { injector: this.injector });
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
