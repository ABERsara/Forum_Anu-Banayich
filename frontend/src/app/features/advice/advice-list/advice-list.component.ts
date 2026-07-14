/**
 * Professional advice list – shows the catalog of professionals.
 */

import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ProfessionalProfile } from '../../../core/models';
import { PROFESSIONAL_DOMAIN_LABELS, ProfessionalDomain } from '../../../core/constants';
import { ProfessionalService } from '../../../core/services/professional.service';

@Component({
  selector: 'app-advice-list',
  standalone: true,
  imports: [RouterLink],
  styleUrl: './advice-list.component.scss',
  template: `
    <div class="page">
      <h1>ייעוץ מקצועי</h1>
      <a routerLink="/advice/qa">לשאלות ותשובות ציבוריות</a>

      @if (professionals().length > 0) {
        <div class="filter-bar">
          <label>
            סינון לפי תחום:
            <select (change)="onDomainChange($event)">
              <option value="">הכל</option>
              @for (domain of domains; track domain) {
                <option [value]="domain">{{ domainLabels[domain] }}</option>
              }
            </select>
          </label>
        </div>
      }

      @if (isLoading()) {
        <p>טוען...</p>
      } @else if (isError()) {
        <p>אירעה שגיאה בטעינת רשימת אנשי המקצוע. נסה שוב מאוחר יותר.</p>
      } @else if (filteredProfessionals().length === 0) {
        <p>לא נמצאו אנשי מקצוע זמינים.</p>
      } @else {
        @for (pro of filteredProfessionals(); track pro.id) {
          <div class="professional-card">
            <strong>{{ pro.first_name }} {{ pro.last_name }}</strong>
            <p>{{ domainLabels[pro.professional_domain] }}</p>
            <p>{{ pro.professional_description }}</p>
            <a [routerLink]="['/advice/ask']" [queryParams]="{ professionalId: pro.id }">
              שאל/י שאלה
            </a>
          </div>
        }
      }
    </div>
  `,
})
export class AdviceListComponent implements OnInit {
  private readonly professionalService = inject(ProfessionalService);

  professionals = signal<ProfessionalProfile[]>([]);
  filteredProfessionals = signal<ProfessionalProfile[]>([]);
  isLoading = signal(false);
  isError = signal(false);
  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;
  readonly domains = Object.values(ProfessionalDomain);

  ngOnInit(): void {
    this.isLoading.set(true);
    this.isError.set(false);
    this.professionalService.getProfessionals().subscribe({
      next: (list) => {
        this.professionals.set(list);
        this.filteredProfessionals.set(list);
        this.isLoading.set(false);
      },
      error: () => {
        this.isError.set(true);
        this.isLoading.set(false);
      },
    });
  }

  onDomainChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as ProfessionalDomain | '';
    this.filteredProfessionals.set(
      value
        ? this.professionals().filter((pro) => pro.professional_domain === value)
        : this.professionals(),
    );
  }
}
