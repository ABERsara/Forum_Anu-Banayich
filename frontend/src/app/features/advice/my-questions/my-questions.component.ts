import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import {
  PROFESSIONAL_DOMAIN_LABELS,
  QUERY_STATUS_LABELS,
  QueryStatus,
} from '../../../core/constants';
import { ProfessionalQuery } from '../../../core/models';
import { LabelService } from '../../../core/i18n/label.service';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-my-questions',
  standalone: true,
  imports: [RouterLink, DatePipe, TranslocoPipe, ErrorDisplayComponent, LoadingSpinnerComponent],
  templateUrl: './my-questions.component.html',
  styleUrl: './my-questions.component.scss',
})
export class MyQuestionsComponent implements OnInit {
  private readonly professionalService = inject(ProfessionalService);
  private readonly labels = inject(LabelService);

  questions: ProfessionalQuery[] = [];
  isLoading = signal(false);
  errorMessage = signal('');

  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;
  readonly statusLabels = QUERY_STATUS_LABELS;
  readonly queryStatus = QueryStatus;

  ngOnInit(): void {
    this.isLoading.set(true);
    this.professionalService.getMyQuestions().subscribe({
      next: (questions) => {
        this.questions = questions;
        this.isLoading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err.error?.detail ?? 'שגיאה בטעינת השאלות שלך.');
        this.isLoading.set(false);
      },
    });
  }

  /**
   * Who the question went to: the professional by name when it was asked of
   * one, otherwise the domain it was posted under. One branch is a name and
   * the other a label key, so this resolves the key itself — a template pipe
   * would have to translate the name too.
   */
  target(question: ProfessionalQuery): string {
    if (question.professional) {
      return `${question.professional.first_name} ${question.professional.last_name}`;
    }
    return question.domain ? this.labels.label(this.domainLabels[question.domain]) : '';
  }
}
