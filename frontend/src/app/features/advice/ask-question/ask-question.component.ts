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

/**
 * Query parameters this screen can be opened with.
 *
 * `professionalId` addresses one named advisor — the advice catalog's "ask
 * this person" link. `domain` addresses a whole discipline, and is what the AI
 * agent chat hands over when a member asks to be referred to a human
 * (ABF-123): the agent knows which profession it covers and the member should
 * not have to name it again. Anything else in the URL is ignored.
 */
const PROFESSIONAL_PARAM = 'professionalId';
const DOMAIN_PARAM = 'domain';

/** The disciplines the select actually offers, for checking a URL against. */
const KNOWN_DOMAINS = new Set<string>(Object.values(ProfessionalDomain));

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

  /** True when the discipline was chosen for the member, not by them. */
  cameWithDomain = false;

  ngOnInit(): void {
    const params = this.route.snapshot.queryParamMap;
    this.professionalId = params.get(PROFESSIONAL_PARAM);
    if (this.professionalId) {
      return;
    }

    const domainControl = this.form.controls.domain;
    domainControl.addValidators(Validators.required);

    // A discipline handed over in the URL is pre-selected rather than
    // enforced: the select stays open, so a member who was referred by an
    // agent about the wrong subject can correct it without going back.
    //
    // Checked against the enum before it is used. A URL is user input, and an
    // unknown value set on the control would be a select with nothing chosen
    // that the required validator nonetheless considers filled.
    const domain = params.get(DOMAIN_PARAM);
    if (domain !== null && KNOWN_DOMAINS.has(domain)) {
      domainControl.setValue(domain as ProfessionalDomain);
      this.cameWithDomain = true;
    }

    domainControl.updateValueAndValidity();
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
