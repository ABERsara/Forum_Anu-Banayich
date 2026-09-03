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
import { TranslocoPipe } from '@jsverse/transloco';

@Component({
  selector: 'app-audit-log',
  standalone: true,
  imports: [RouterLink, TranslocoPipe],
  template: `
    <!-- No direction here: the page inherits it from <html dir>, which
         LocaleService sets from the active language (CONTRIBUTING §6). -->
    <div style="padding: 1rem">
      <a routerLink="/admin">← {{ 'admin.back_to_dashboard' | transloco }}</a>
      <h1>{{ 'admin.audit_log.title' | transloco }}</h1>
      <!-- TODO: the table, the action filter and the pagination are all still
           to be written, and their copy needs keys of its own under
           admin.audit_log.* when they are. -->
      <p>TODO: implement audit log viewer</p>
    </div>
  `,
})
export class AuditLogComponent {}
