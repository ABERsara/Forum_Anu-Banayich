/**
 * Pending registrations – admin approval queue.
 *
 * TODO (G2b/G2c):
 *   1. "בדיקה" button → expand to show details + documents
 *   2. Expanded view shows:
 *      - All personal details
 *      - Document links (presigned URLs from backend)
 *      - "אישור" and "דחייה" buttons
 *   3. Rejection requires a reason text input
 *   4. After approve/reject: remove from list and refresh
 *
 * Remember: Two admins must approve. The backend tracks who already approved.
 */

import { Component, OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';

import { UserAdminView } from '../../../core/models';
import { ACCOUNT_STATUS_LABELS, SECTOR_LABELS, USER_TYPE_LABELS } from '../../../core/constants';
import { AdminService } from '../../../core/services/admin.service';

@Component({
  selector: 'app-pending-registrations',
  standalone: true,
  imports: [RouterLink, DatePipe],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <a routerLink="/admin">← חזרה ללוח הבקרה</a>
      <h1>הרשמות ממתינות לאישור</h1>

      @if (isLoading) {
        <p>טוען...</p>
      } @else if (hasError) {
        <p>אירעה שגיאה בטעינת ההרשמות. נסי לרענן את הדף.</p>
      } @else if (registrations.length === 0) {
        <p>אין הרשמות ממתינות כרגע.</p>
      } @else {
        @for (reg of registrations; track reg.id) {
          <div style="border: 1px solid #ccc; margin: 0.5rem 0; padding: 1rem; border-radius: 8px">
            <strong>{{ reg.first_name }} {{ reg.last_name }}</strong>
            <span> | {{ reg.email }}</span>
            <span> | {{ userTypeLabels[reg.user_type!] }} | {{ sectorLabels[reg.sector!] }}</span>
            <span> | {{ reg.created_at | date }}</span>
            <span> | {{ statusLabels[reg.account_status] }}</span>
            <!-- TODO: expand to show documents + approve/reject buttons -->
            <div>
              <button (click)="approve(reg.id)">אישור</button>
              <button (click)="reject(reg.id)">דחייה</button>
            </div>
          </div>
        }
      }
    </div>
  `,
})
export class PendingRegistrationsComponent implements OnInit {
  private readonly adminService = inject(AdminService);

  registrations: UserAdminView[] = [];
  isLoading = false;
  hasError = false;
  readonly userTypeLabels = USER_TYPE_LABELS;
  readonly sectorLabels = SECTOR_LABELS;
  readonly statusLabels = ACCOUNT_STATUS_LABELS;

  ngOnInit(): void {
    this.isLoading = true;
    this.hasError = false;
    this.adminService.getPendingRegistrations().subscribe({
      next: (result) => {
        this.registrations = result;
        this.isLoading = false;
      },
      error: () => {
        this.hasError = true;
        this.isLoading = false;
      },
    });
  }

  approve(userId: string): void {
    void userId;
    // TODO: call adminService.approveRegistration(userId) (G2b)
  }

  reject(userId: string): void {
    void userId;
    // TODO: show reason input, then call adminService.rejectRegistration(userId, reason) (G2b)
  }
}
