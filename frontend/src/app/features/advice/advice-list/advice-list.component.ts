/**
 * Professional advice list – shows the catalog of professionals.
 */

import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { ProfessionalProfile } from '../../../core/models';
import { PROFESSIONAL_DOMAIN_LABELS, ProfessionalDomain } from '../../../core/constants';
import { ProfessionalService } from '../../../core/services/professional.service';

@Component({
  selector: 'app-advice-list',
  standalone: true,
  imports: [RouterLink, TranslocoPipe],
  styleUrl: './advice-list.component.scss',
  template: `
    <!-- No dir here: text direction follows <html dir>, which LocaleService
         sets from the active language (CONTRIBUTING §6). -->
    <div class="page">
      <h1>{{ 'advice.list.title' | transloco }}</h1>
      <div class="top-links">
        <a routerLink="/advice/qa">{{ 'advice.list.public_qa_link' | transloco }}</a>
        <span class="separator" aria-hidden="true">|</span>
        <!-- The link names the page it opens, so it shares that page's key
             rather than holding a second copy of the same words. -->
        <a routerLink="/advice/my-questions">{{ 'advice.my_questions.title' | transloco }}</a>
      </div>

      @if (professionals().length > 0) {
        <div class="filter-bar">
          <label>
            {{ 'advice.list.filter_label' | transloco }}
            <select (change)="onDomainChange($event)">
              <option value="">{{ 'advice.list.filter_all' | transloco }}</option>
              @for (domain of domains; track domain) {
                <option [value]="domain">{{ domainLabels[domain] | transloco }}</option>
              }
            </select>
          </label>
        </div>
      }

      @if (isLoading()) {
        <p>{{ 'common.loading' | transloco }}</p>
      } @else if (isError()) {
        <p>{{ 'advice.errors.load_professionals_failed' | transloco }}</p>
      } @else if (filteredProfessionals().length === 0) {
        <p>{{ 'advice.list.empty' | transloco }}</p>
      } @else {
        @for (pro of filteredProfessionals(); track pro.id) {
          <div class="professional-card">
            <!-- The professional's name and their own description are content
                 they wrote, not UI: shown as they came, in either language. -->
            <strong>{{ pro.first_name }} {{ pro.last_name }}</strong>
            <p>{{ domainLabels[pro.professional_domain] | transloco }}</p>
            <p>{{ pro.professional_description }}</p>
            <a [routerLink]="['/advice/ask']" [queryParams]="{ professionalId: pro.id }">
              {{ 'advice.list.ask_link' | transloco }}
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
