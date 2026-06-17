/**
 * Audit log viewer – admin only.
 *
 * TODO:
 *   1. On init: call ReportService.getAuditLog()
 *   2. Display in a table: timestamp, actor name, action, entity type, entity id
 *   3. Implement pagination (50 per page)
 *   4. Add filter by action type (dropdown)
 *   5. Show details (JSON) on click/expand
 */

import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-audit-log',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <a routerLink="/admin">← חזרה ללוח הבקרה</a>
      <h1>יומן פעולות (Audit Log)</h1>
      <p>TODO: implement audit log viewer</p>
    </div>
  `,
})
export class AuditLogComponent {}
