import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import {
  FormBuilder,
  FormControl,
  FormRecord,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { RouterLink } from '@angular/router';

import { PROFESSIONAL_DOMAIN_LABELS } from '../../../core/constants';
import { ProfessionalQuery } from '../../../core/models';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

/** Mirrors ProfessionalAnswerRequest in backend/app/schemas/professional.py. */
const ANSWER_MIN_LENGTH = 10;
const ANSWER_MAX_LENGTH = 5000;

/**
 * The professional's work queue: every question still waiting for their answer,
 * each with its own answer box.
 *
 * The asker is identified by their group–sector alias, never by name, unless
 * they chose to reveal it when asking (SPEC §6.4).
 */
@Component({
  selector: 'app-pending-questions',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
  templateUrl: './pending-questions.component.html',
  styleUrl: './pending-questions.component.scss',
})
export class PendingQuestionsComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly professionalService = inject(ProfessionalService);

  /** One answer control per pending question, keyed by question id. */
  readonly answers = new FormRecord<FormControl<string>>({});

  readonly questions = signal<ProfessionalQuery[]>([]);
  readonly isLoading = signal(false);
  readonly errorMessage = signal('');
  readonly successMessage = signal('');
  /** Id of the question being submitted, so only its own button is disabled. */
  readonly submittingId = signal<string | null>(null);

  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;
  readonly answerMaxLength = ANSWER_MAX_LENGTH;

  ngOnInit(): void {
    this.isLoading.set(true);
    this.professionalService.getPendingQuestions().subscribe({
      next: (questions) => {
        this.questions.set(questions);
        for (const question of questions) {
          this.answers.addControl(question.id, this.newAnswerControl());
        }
        this.isLoading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err.error?.detail ?? 'שגיאה בטעינת השאלות הממתינות.');
        this.isLoading.set(false);
      },
    });
  }

  answerControl(question: ProfessionalQuery): FormControl<string> {
    return this.answers.controls[question.id];
  }

  /**
   * What this professional may see about the asker: their real name only if
   * they chose to reveal it, otherwise the "group – sector" alias.
   */
  askerLabel(question: ProfessionalQuery): string {
    return question.asker
      ? `${question.asker.first_name} ${question.asker.last_name}`
      : question.asker_alias;
  }

  /** The domain a general question arrived under; empty when asked directly. */
  topic(question: ProfessionalQuery): string {
    return question.domain ? this.domainLabels[question.domain] : '';
  }

  submit(question: ProfessionalQuery): void {
    const control = this.answerControl(question);
    if (control.invalid) {
      control.markAsTouched();
      return;
    }

    this.submittingId.set(question.id);
    this.errorMessage.set('');
    this.successMessage.set('');

    this.professionalService.answerQuestion(question.id, control.value).subscribe({
      next: () => {
        // Answered, so it is no longer pending: drop it from the queue and
        // release its control instead of leaving a stale one behind.
        this.questions.update((pending) => pending.filter((q) => q.id !== question.id));
        this.answers.removeControl(question.id);
        this.successMessage.set('התשובה נשלחה, והשואל/ת קיבל/ה על כך התראה במייל.');
        this.submittingId.set(null);
      },
      error: (err) => {
        this.errorMessage.set(err.error?.detail ?? 'שגיאה בשליחת התשובה.');
        this.submittingId.set(null);
      },
    });
  }

  private newAnswerControl(): FormControl<string> {
    return this.fb.nonNullable.control('', [
      Validators.required,
      Validators.minLength(ANSWER_MIN_LENGTH),
      Validators.maxLength(ANSWER_MAX_LENGTH),
    ]);
  }
}
