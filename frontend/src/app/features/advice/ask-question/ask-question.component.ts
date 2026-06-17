/**
 * Ask a professional question.
 *
 * TODO:
 *   1. Read ?professionalId=... from query params (optional – for direct questions)
 *   2. If professionalId exists: show the professional's name and domain
 *   3. Form fields:
 *      - content (required, 10–2000 chars)
 *      - is_public (checkbox: "האם לפרסם את השאלה והתשובה לחברי הקהילה?")
 *      - show_real_name (checkbox: "הצג את שמי האמיתי לאיש המקצוע")
 *      - domain (dropdown – only shown when no professionalId)
 *   4. On submit: call ProfessionalService.askQuestion()
 *   5. On success: navigate back to /advice + show success toast
 */

import { Component, OnInit, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { PROFESSIONAL_DOMAIN_LABELS, ProfessionalDomain } from '../../../core/constants';
import { ProfessionalService } from '../../../core/services/professional.service';

@Component({
  selector: 'app-ask-question',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <a routerLink="/advice">← חזרה לרשימת אנשי מקצוע</a>
      <h1>שאלה מקצועית</h1>

      <!-- TODO: show professional name if professionalId in query params -->
      <!-- TODO: build real form -->
      <p>TODO: implement ask question form</p>
    </div>
  `,
})
export class AskQuestionComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(FormBuilder);
  private readonly professionalService = inject(ProfessionalService);

  professionalId: string | null = null;
  readonly domainOptions = Object.values(ProfessionalDomain);
  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;

  form = this.fb.group({
    content: ['', [Validators.required, Validators.minLength(10), Validators.maxLength(2000)]],
    is_public: [false],
    show_real_name: [false],
    domain: [null as ProfessionalDomain | null],
  });

  ngOnInit(): void {
    this.professionalId = this.route.snapshot.queryParamMap.get('professionalId');
  }

  onSubmit(): void {
    if (this.form.invalid) return;
    // TODO: implement
  }
}
