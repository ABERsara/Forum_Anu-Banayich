/**
 * Manage professionals – admin page to add/edit professionals.
 *
 * TODO:
 *   1. List all professional users
 *   2. "הוסף איש מקצוע" button → form to invite/create a professional
 *   3. Edit each professional:
 *      - domain, groups (which user types they serve), sectors, description
 *      - Active toggle
 *   4. Call PUT /admin/professionals/:id on save
 */

import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-manage-professionals',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <a routerLink="/admin">← חזרה ללוח הבקרה</a>
      <h1>ניהול אנשי מקצוע</h1>
      <p>TODO: implement professionals management</p>
    </div>
  `,
})
export class ManageProfessionalsComponent {}
