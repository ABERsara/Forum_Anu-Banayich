/**
 * Public Q&A feed – shows publicly answered questions.
 *
 * This is the "community knowledge" section (ידע קהילתי).
 *
 * TODO:
 *   1. On init: call ProfessionalService.getPublicQA()
 *   2. Show filter by domain (dropdown)
 *   3. Each item shows: question, answer, domain, date answered
 *   4. Mark "מועדפות" (featured) with a star icon
 *   5. Implement pagination
 */

import { Component, OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { PublicQA } from '../../../core/models';
import { PROFESSIONAL_DOMAIN_LABELS, ProfessionalDomain } from '../../../core/constants';
import { ProfessionalService } from '../../../core/services/professional.service';

@Component({
  selector: 'app-qa-feed',
  standalone: true,
  imports: [RouterLink, TranslocoPipe],
  template: `
    <!-- No direction here: the page inherits it from <html dir>, which
         LocaleService sets from the active language (CONTRIBUTING §6). -->
    <div style="padding: 1rem">
      <a routerLink="/advice">← {{ 'advice.qa_feed.back_to_advice' | transloco }}</a>
      <h1>{{ 'advice.qa_feed.title' | transloco }}</h1>
      <!-- TODO: domain filter, list of Q&As, pagination — all still to be
           written, and their copy needs keys of its own under advice.qa_feed.*
           when it is. -->
      <p>TODO: implement Q&A feed</p>
    </div>
  `,
})
export class QaFeedComponent implements OnInit {
  private readonly professionalService = inject(ProfessionalService);

  qaItems: PublicQA[] = [];
  isLoading = false;
  selectedDomain: ProfessionalDomain | null = null;
  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;

  ngOnInit(): void {
    this.loadQA();
  }

  private loadQA(): void {
    this.isLoading = true;
    // TODO: implement
    this.isLoading = false;
  }
}
