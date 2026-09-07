/**
 * User profile component.
 *
 * TODO:
 *   1. Display current user info (from AuthService.currentUser())
 *   2. Show user_type and sector with translated labels
 *   3. Show account_status with translated label + explanation
 *   4. Allow updating: first_name, last_name (add PUT /users/me endpoint if not done)
 *   5. Add "מחיקת חשבון" section at the bottom (dangerous – requires OTP confirmation)
 *
 * The screen owns no direction of its own (ABF-136): `LocaleService` sets
 * `<html dir>` from the active language and the page inherits it, so the
 * `direction: rtl` that used to sit in the inline style would have pinned the
 * layout to RTL on an English page — the one thing this migration is for.
 */

import { Component, inject } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';

import { ACCOUNT_STATUS_LABELS, SECTOR_LABELS, USER_TYPE_LABELS } from '../../core/constants';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [TranslocoPipe],
  template: `
    <div style="padding: 1rem">
      <h1>{{ 'profile.title' | transloco }}</h1>

      @if (auth.currentUser(); as user) {
        <p>
          <strong>{{ 'profile.name_label' | transloco }}</strong> {{ user.first_name }}
          {{ user.last_name }}
        </p>
        <p>
          <strong>{{ 'profile.email_label' | transloco }}</strong> {{ user.email }}
        </p>
        <p>
          <strong>{{ 'profile.group_label' | transloco }}</strong>
          {{ user.user_type ? (userTypeLabels[user.user_type] | transloco) : '' }}
        </p>
        <p>
          <strong>{{ 'profile.sector_label' | transloco }}</strong>
          {{ user.sector ? (sectorLabels[user.sector] | transloco) : '' }}
        </p>
        <p>
          <strong>{{ 'profile.status_label' | transloco }}</strong>
          {{ statusLabels[user.account_status] | transloco }}
        </p>
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
