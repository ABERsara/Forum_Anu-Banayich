/**
 * Admin dashboard – overview of the system.
 *
 * TODO:
 *   1. Show stats cards:
 *      - Pending registrations count (badge with count)
 *      - Active users count
 *      - Pending reports count
 *   2. Quick links to /admin/registrations, /admin/professionals, /admin/audit-log
 *   3. Recent audit log entries (last 10 actions)
 */

import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-admin-dashboard',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <h1>לוח בקרה – מנהל</h1>
      <nav>
        <a routerLink="/admin/registrations">הרשמות ממתינות</a> |
        <a routerLink="/admin/professionals">ניהול אנשי מקצוע</a> |
        <a routerLink="/admin/audit-log">יומן פעולות</a> |
        <a routerLink="/moderator/reports">דיווחים</a>
      </nav>
      <!-- TODO: stats cards, recent audit entries -->
      <p>TODO: implement admin dashboard</p>
    </div>
  `,
})
export class AdminDashboardComponent {}
