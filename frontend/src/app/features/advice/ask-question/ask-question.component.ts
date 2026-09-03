import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { TranslocoPipe } from '@jsverse/transloco';

import { PROFESSIONAL_DOMAIN_LABELS, ProfessionalDomain } from '../../../core/constants';
import { ProfessionalQueryCreate } from '../../../core/models';
import { ProfessionalService } from '../../../core/services/professional.service';
import { AdviceError, NO_ERROR, adviceErrorFrom } from '../advice-error';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-ask-question',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
  templateUrl: './ask-question.component.html',
  styleUrl: './ask-question.component.scss',
})
export class AskQuestionComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  private readonly professionalService = inject(ProfessionalService);

  professionalId: string | null = null;
  readonly domainOptions = Object.values(ProfessionalDomain);
  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;

  isLoading = signal(false);
  /** What went wrong on submit, as a key of ours or a sentence the API sent. */
  error = signal<AdviceError>(NO_ERROR);

  form = this.fb.group({
    content: ['', [Validators.required, Validators.minLength(10), Validators.maxLength(2000)]],
    is_public: [false],
    show_real_name: [false],
    domain: [null as ProfessionalDomain | null],
  });

  get contentLength(): number {
    return this.form.get('content')?.value?.length ?? 0;
  }

  ngOnInit(): void {
    this.professionalId = this.route.snapshot.queryParamMap.get('professionalId');
    if (!this.professionalId) {
      const domainControl = this.form.controls.domain;
      domainControl.addValidators(Validators.required);
      domainControl.updateValueAndValidity();
    }
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.isLoading.set(true);
    this.error.set(NO_ERROR);

    const { content, is_public, show_real_name, domain } = this.form.getRawValue();
    const data: ProfessionalQueryCreate = {
      content: content ?? '',
      is_public: is_public ?? false,
      show_real_name: show_real_name ?? false,
      ...(this.professionalId
        ? { professional_id: this.professionalId }
        : { domain: domain ?? undefined }),
    };

    this.professionalService.askQuestion(data).subscribe({
      next: () => {
        this.isLoading.set(false);
        this.router.navigate(['/advice']);
      },
      error: (err) => {
        this.error.set(adviceErrorFrom(err, 'advice.errors.ask_failed'));
        this.isLoading.set(false);
      },
    });
  }
}
