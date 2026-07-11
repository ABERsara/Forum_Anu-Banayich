/**
 * Pending registrations – admin approval queue.
 *
 * TODO (G2c):
 *   1. "בדיקה" button → expand to show details + documents
 *   2. Expanded view shows:
 *      - All personal details
 *      - Document links (presigned URLs from backend)
 *
 * Remember: Two admins must approve. The backend tracks who already approved.
 */

import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';

import { UserAdminView } from '../../../core/models';
import {
  AccountStatus,
  ACCOUNT_STATUS_LABELS,
  SECTOR_LABELS,
  USER_TYPE_LABELS,
} from '../../../core/constants';
import { AdminService } from '../../../core/services/admin.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';

@Component({
  selector: 'app-pending-registrations',
  standalone: true,
  imports: [RouterLink, DatePipe, ConfirmDialogComponent],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <a routerLink="/admin">← חזרה ללוח הבקרה</a>
      <h1>הרשמות ממתינות לאישור</h1>

      @if (actionError()) {
        <p style="color: #dc2626">{{ actionError() }}</p>
      }

      @if (isLoading()) {
        <p>טוען...</p>
      } @else if (hasError()) {
        <p>אירעה שגיאה בטעינת ההרשמות. נסי לרענן את הדף.</p>
      } @else if (registrations().length === 0) {
        <p>אין הרשמות ממתינות כרגע.</p>
      } @else {
        @for (reg of registrations(); track reg.id) {
          <div style="border: 1px solid #ccc; margin: 0.5rem 0; padding: 1rem; border-radius: 8px">
            <strong>{{ reg.first_name }} {{ reg.last_name }}</strong>
            <span> | {{ reg.email }}</span>
            <span> | {{ userTypeLabels[reg.user_type!] }} | {{ sectorLabels[reg.sector!] }}</span>
            <span> | {{ reg.created_at | date }}</span>
            <span> | {{ statusLabels[reg.account_status] }}</span>
            <!-- TODO: expand to show documents (G2c) -->
            <div>
              <button (click)="approve(reg.id)">אישור</button>
              <button (click)="reject(reg.id)">דחייה</button>
            </div>
          </div>
        }
      }

      @if (rejectingId()) {
        <app-confirm-dialog
          title="דחיית הרשמה"
          message="פעולה זו תדחה את ההרשמה ותשלח למועמד הודעה עם הסיבה."
          confirmText="דחייה"
          [isDestructive]="true"
          [requireInput]="true"
          inputLabel="סיבת הדחייה"
          inputPlaceholder="לדוגמה: מסמכים חסרים"
          [inputMinLength]="5"
          (confirmed)="confirmReject($event)"
          (cancelled)="cancelReject()"
        />
      }
    </div>
  `,
})
export class PendingRegistrationsComponent implements OnInit {
  private readonly adminService = inject(AdminService);

  registrations = signal<UserAdminView[]>([]);
  isLoading = signal(false);
  hasError = signal(false);
  actionError = signal<string | null>(null);
  rejectingId = signal<string | null>(null);
  readonly userTypeLabels = USER_TYPE_LABELS;
  readonly sectorLabels = SECTOR_LABELS;
  readonly statusLabels = ACCOUNT_STATUS_LABELS;

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

  approve(userId: string): void {
    this.actionError.set(null);
    this.adminService.approveRegistration(userId).subscribe({
      next: (updated) => this.applyUpdate(updated),
      error: (err: HttpErrorResponse) =>
        this.actionError.set(err.error?.detail ?? 'אירעה שגיאה באישור ההרשמה. נסה שוב.'),
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
        this.actionError.set(err.error?.detail ?? 'אירעה שגיאה בדחיית ההרשמה. נסה שוב.'),
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
        : this.registrations().filter((reg) => reg.id !== updated.id)
    );
  }
}
