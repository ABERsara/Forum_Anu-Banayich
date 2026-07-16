import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { PROFESSIONAL_DOMAIN_LABELS, QUERY_STATUS_LABELS } from '../../../core/constants';
import { ProfessionalQuery } from '../../../core/models';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-my-questions',
  standalone: true,
  imports: [RouterLink, DatePipe, ErrorDisplayComponent, LoadingSpinnerComponent],
  templateUrl: './my-questions.component.html',
  styleUrl: './my-questions.component.scss',
})
export class MyQuestionsComponent implements OnInit {
  private readonly professionalService = inject(ProfessionalService);

  questions: ProfessionalQuery[] = [];
  isLoading = signal(false);
  errorMessage = signal('');

  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;
  readonly statusLabels = QUERY_STATUS_LABELS;

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

  target(question: ProfessionalQuery): string {
    if (question.professional) {
      return `${question.professional.first_name} ${question.professional.last_name}`;
    }
    return question.domain ? this.domainLabels[question.domain] : '';
  }
}
