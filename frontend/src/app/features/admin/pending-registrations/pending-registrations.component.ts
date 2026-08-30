/**
 * Pending registrations – the admin approval queue and the review of a single
 * request.
 *
 * The queue lists who is waiting; opening a row loads that registration in
 * full (GET /admin/registrations/{id}) so the admin can weigh the applicant's
 * details and the documents filed with them before approving or rejecting.
 *
 * Documents are metadata only — what was uploaded, when, and until when it is
 * valid. The presigned URLs that open the files themselves (SPEC §9.1) are
 * still in the backlog, so nothing here is a link.
 *
 * Remember: two admins must approve. The backend tracks who already approved,
 * and the open row shows how far that got.
 */

import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { TranslocoPipe } from '@jsverse/transloco';

import { DocumentAdminView, RegistrationDetail, UserAdminView } from '../../../core/models';
import {
  AccountStatus,
  ACCOUNT_STATUS_LABELS,
  DOCUMENT_TYPE_LABELS,
  SECTOR_LABELS,
  USER_TYPE_LABELS,
} from '../../../core/constants';
import { LabelService } from '../../../core/i18n/label.service';
import { AdminService } from '../../../core/services/admin.service';
import { ButtonComponent } from '../../../shared/components/button/button.component';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

/** Stands in for a detail the applicant did not provide. */
const NOT_PROVIDED = 'לא צוין';

@Component({
  selector: 'app-pending-registrations',
  standalone: true,
  imports: [
    RouterLink,
    DatePipe,
    TranslocoPipe,
    ButtonComponent,
    ConfirmDialogComponent,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
  templateUrl: './pending-registrations.component.html',
  styleUrl: './pending-registrations.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PendingRegistrationsComponent implements OnInit {
  private readonly adminService = inject(AdminService);
  private readonly labels = inject(LabelService);

  registrations = signal<UserAdminView[]>([]);
  isLoading = signal(false);
  hasError = signal(false);
  actionError = signal<string | null>(null);
  rejectingId = signal<string | null>(null);

  /** The registration whose details are open; null while every row is collapsed. */
  readonly openId = signal<string | null>(null);
  /** The open registration in full. Null while it is still loading, or failed to. */
  readonly detail = signal<RegistrationDetail | null>(null);
  readonly isDetailLoading = signal(false);
  readonly detailError = signal('');

  readonly userTypeLabels = USER_TYPE_LABELS;
  readonly sectorLabels = SECTOR_LABELS;
  readonly statusLabels = ACCOUNT_STATUS_LABELS;
  readonly documentTypeLabels = DOCUMENT_TYPE_LABELS;
  readonly notProvided = NOT_PROVIDED;

  ngOnInit(): void {
    this.isLoading.set(true);
    this.hasError.set(false);
    this.adminService.getPendingRegistrations().subscribe({
      next: (result) => {
        this.registrations.set(result);
        this.isLoading.set(false);
      },
      error: () => {
        this.hasError.set(true);
        this.isLoading.set(false);
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Reviewing one registration
  // ---------------------------------------------------------------------------

  isOpen(userId: string): boolean {
    return this.openId() === userId;
  }

  /**
   * Opens a registration for review, or closes it if it is already open.
   *
   * One row at a time: the details are what the admin is deciding on, and two
   * applicants open side by side is how the wrong one gets approved. Each
   * opening refetches — another admin may have approved or rejected the
   * request since this queue was loaded.
   */
  toggleDetail(userId: string): void {
    if (this.isOpen(userId)) {
      this.closeDetail();
      return;
    }

    this.openId.set(userId);
    this.detail.set(null);
    this.detailError.set('');
    this.isDetailLoading.set(true);

    this.adminService.getRegistration(userId).subscribe({
      next: (detail) => {
        // A second click may have moved on to another row while this was in
        // flight; that row's own response is the one that belongs on screen.
        if (!this.isOpen(userId)) {
          return;
        }
        this.detail.set(detail);
        this.isDetailLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        if (!this.isOpen(userId)) {
          return;
        }
        this.detailError.set(
          this.messageFrom(err, 'אירעה שגיאה בטעינת פרטי הבקשה. נסי לרענן את הדף.'),
        );
        this.isDetailLoading.set(false);
      },
    });
  }

  closeDetail(): void {
    this.openId.set(null);
    this.detail.set(null);
    this.detailError.set('');
    this.isDetailLoading.set(false);
  }

  // ---------------------------------------------------------------------------
  // Reading helpers for the open registration
  // ---------------------------------------------------------------------------

  fullName(registration: UserAdminView): string {
    return `${registration.first_name} ${registration.last_name}`;
  }

  /** A detail the applicant may have left empty reads as "לא צוין", never blank. */
  orNotProvided(value: string | null): string {
    return value?.trim() ? value : NOT_PROVIDED;
  }

  /**
   * The bereavement group and the sector are nullable on the model — the
   * sector especially, because it is the admin who assigns the final cell
   * while reviewing (SPEC §8.1), so a request can reach this screen without one.
   */
  userTypeLabel(registration: UserAdminView): string {
    return registration.user_type
      ? this.labels.label(this.userTypeLabels[registration.user_type])
      : NOT_PROVIDED;
  }

  sectorLabel(registration: UserAdminView): string {
    return registration.sector
      ? this.labels.label(this.sectorLabels[registration.sector])
      : NOT_PROVIDED;
  }

  /** Where this request stands in the two-admin approval (SPEC §8.2). */
  approvalProgress(registration: UserAdminView): string {
    return registration.first_approver_id
      ? 'מנהל אחד כבר אישר — נדרש אישור של מנהל נוסף.'
      : 'טרם אושרה — נדרשים אישורים של שני מנהלים.';
  }

  documentLabel(document: DocumentAdminView): string {
    return this.labels.label(this.documentTypeLabels[document.doc_type]);
  }

  // ---------------------------------------------------------------------------
  // Approve / reject
  // ---------------------------------------------------------------------------

  approve(userId: string): void {
    this.actionError.set(null);
    this.adminService.approveRegistration(userId).subscribe({
      next: (updated) => this.applyUpdate(updated),
      error: (err: HttpErrorResponse) =>
        this.actionError.set(this.messageFrom(err, 'אירעה שגיאה באישור ההרשמה. נסה שוב.')),
    });
  }

  reject(userId: string): void {
    this.actionError.set(null);
    this.rejectingId.set(userId);
  }

  cancelReject(): void {
    this.rejectingId.set(null);
  }

  confirmReject(reason: string): void {
    const userId = this.rejectingId();
    if (!userId) {
      return;
    }
    this.adminService.rejectRegistration(userId, reason).subscribe({
      next: (updated) => {
        this.applyUpdate(updated);
        this.rejectingId.set(null);
      },
      error: (err: HttpErrorResponse) =>
        this.actionError.set(this.messageFrom(err, 'אירעה שגיאה בדחיית ההרשמה. נסה שוב.')),
    });
  }

  /** Updates the row in place, or removes it once it leaves the pending queue (active/rejected). */
  private applyUpdate(updated: UserAdminView): void {
    const stillPending =
      updated.account_status === AccountStatus.PENDING_APPROVAL ||
      updated.account_status === AccountStatus.PARTIALLY_APPROVED;

    this.registrations.set(
      stillPending
        ? this.registrations().map((reg) => (reg.id === updated.id ? updated : reg))
        : this.registrations().filter((reg) => reg.id !== updated.id),
    );

    if (!this.isOpen(updated.id)) {
      return;
    }
    if (stillPending) {
      // The decision just made is part of what the open panel reports, and the
      // documents it already holds did not change.
      this.detail.update((open) => (open ? { ...open, ...updated } : open));
    } else {
      // Reviewing a settled registration is what the endpoint refuses (403),
      // so the panel closes with the row it belonged to.
      this.closeDetail();
    }
  }

  private messageFrom(err: HttpErrorResponse, fallback: string): string {
    const detail: unknown = err.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }
}
