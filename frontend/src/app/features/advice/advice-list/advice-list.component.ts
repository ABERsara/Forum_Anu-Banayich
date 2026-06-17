/**
 * Professional advice list – shows the catalog of professionals.
 *
 * TODO:
 *   1. On init: call ProfessionalService.getProfessionals()
 *   2. Display each professional as a card:
 *      name, domain (use PROFESSIONAL_DOMAIN_LABELS), short description
 *   3. Each card has a "שאל/י שאלה" button → navigate to /advice/ask?professionalId=...
 *   4. Add "שאלות ותשובות ציבוריות" link → /advice/qa
 *   5. Filter bar: filter by domain (optional, client-side)
 *   6. No contact details shown (privacy rule!)
 */

import { Component, OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ProfessionalProfile } from '../../../core/models';
import { PROFESSIONAL_DOMAIN_LABELS } from '../../../core/constants';
import { ProfessionalService } from '../../../core/services/professional.service';

@Component({
  selector: 'app-advice-list',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <h1>ייעוץ מקצועי</h1>
      <a routerLink="/advice/qa">לשאלות ותשובות ציבוריות</a>

      @if (isLoading) {
        <p>טוען...</p>
      } @else {
        @for (pro of professionals; track pro.id) {
          <div style="border: 1px solid #ccc; margin: 0.5rem 0; padding: 1rem; border-radius: 8px">
            <strong>{{ pro.first_name }} {{ pro.last_name }}</strong>
            <p>{{ domainLabels[pro.professional_domain] }}</p>
            <p>{{ pro.professional_description }}</p>
            <a [routerLink]="['/advice/ask']" [queryParams]="{ professionalId: pro.id }">
              שאל/י שאלה
            </a>
          </div>
        }
      }
      <!-- TODO: add empty state -->
    </div>
  `,
})
export class AdviceListComponent implements OnInit {
  private readonly professionalService = inject(ProfessionalService);

  professionals: ProfessionalProfile[] = [];
  isLoading = false;
  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;

  ngOnInit(): void {
    this.isLoading = true;
    // TODO: uncomment when service is implemented
    // this.professionalService.getProfessionals().subscribe({
    //   next: (list) => { this.professionals = list; this.isLoading = false; },
    //   error: () => { this.isLoading = false; },
    // });
    this.isLoading = false;
  }
}
