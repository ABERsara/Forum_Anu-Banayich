/**
 * User profile component.
 *
 * TODO:
 *   1. Display current user info (from AuthService.currentUser())
 *   2. Show user_type and sector with Hebrew labels
 *   3. Show account_status with Hebrew label + explanation
 *   4. Allow updating: first_name, last_name (add PUT /users/me endpoint if not done)
 *   5. Add "מחיקת חשבון" section at the bottom (dangerous – requires OTP confirmation)
 */

import { Component, inject } from '@angular/core';

import { ACCOUNT_STATUS_LABELS, SECTOR_LABELS, USER_TYPE_LABELS } from '../../core/constants';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-profile',
  standalone: true,
  template: `
    <div style="padding: 1rem; direction: rtl">
      <h1>הפרופיל שלי</h1>

      @if (auth.currentUser(); as user) {
        <p><strong>שם:</strong> {{ user.first_name }} {{ user.last_name }}</p>
        <p><strong>מייל:</strong> {{ user.email }}</p>
        <p><strong>קבוצה:</strong> {{ user.user_type ? userTypeLabels[user.user_type] : '' }}</p>
        <p><strong>מגזר:</strong> {{ user.sector ? sectorLabels[user.sector] : '' }}</p>
        <p><strong>סטטוס:</strong> {{ statusLabels[user.account_status] }}</p>
        <!-- TODO: edit form, change password, delete account -->
      }
    </div>
  `,
})
export class ProfileComponent {
  readonly auth = inject(AuthService);
  readonly userTypeLabels = USER_TYPE_LABELS;
  readonly sectorLabels = SECTOR_LABELS;
  readonly statusLabels = ACCOUNT_STATUS_LABELS;
}
