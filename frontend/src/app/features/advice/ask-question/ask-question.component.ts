import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { PROFESSIONAL_DOMAIN_LABELS, ProfessionalDomain } from '../../../core/constants';
import { ProfessionalQueryCreate } from '../../../core/models';
import { ProfessionalService } from '../../../core/services/professional.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-ask-question',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, ErrorDisplayComponent, LoadingSpinnerComponent],
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
  errorMessage = signal('');

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
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set('');

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
      next: () => this.router.navigate(['/advice']),
      error: (err) => {
        this.errorMessage.set(err.error?.detail ?? 'שגיאה בשליחת השאלה.');
        this.isLoading.set(false);
      },
    });
  }
}
