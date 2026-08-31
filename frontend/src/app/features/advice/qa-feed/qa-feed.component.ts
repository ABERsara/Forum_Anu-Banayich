/**
 * Public Q&A feed – shows publicly answered questions.
 *
 * This is the "community knowledge" section (ידע קהילתי).
 */

import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { PROFESSIONAL_DOMAIN_LABELS, ProfessionalDomain } from '../../../core/constants';
import { PublicQA } from '../../../core/models';
import { ProfessionalService } from '../../../core/services/professional.service';
import { errorKeyFrom } from '../../../core/utils/error-key.util';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

const PAGE_SIZE = 20;

@Component({
  selector: 'app-qa-feed',
  standalone: true,
  imports: [RouterLink, DatePipe, TranslocoPipe, ErrorDisplayComponent, LoadingSpinnerComponent],
  templateUrl: './qa-feed.component.html',
  styleUrl: './qa-feed.component.scss',
})
export class QaFeedComponent implements OnInit {
  private readonly professionalService = inject(ProfessionalService);

  items = signal<PublicQA[]>([]);
  isLoading = signal(false);
  isLoadingMore = signal(false);
  hasError = signal(false);
  errorKey = signal('errors.generic');
  hasMore = signal(false);
  selectedDomain = signal<ProfessionalDomain | ''>('');
  /** Id of the item whose like toggle just failed, so only that card shows the error. */
  likeErrorId = signal<string | null>(null);

  private page = 1;

  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;
  readonly domains = Object.values(ProfessionalDomain);

  ngOnInit(): void {
    this.load(true);
  }

  onDomainChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as ProfessionalDomain | '';
    this.selectedDomain.set(value);
    this.load(true);
  }

  loadMore(): void {
    this.load(false);
  }

  toggleLike(item: PublicQA): void {
    this.likeErrorId.set(null);
    this.professionalService.toggleLike(item.id).subscribe({
      next: (result) => {
        this.items.update((current) =>
          current.map((existing) =>
            existing.id === item.id
              ? { ...existing, liked_by_me: result.liked, like_count: result.like_count }
              : existing,
          ),
        );
      },
      error: () => {
        this.likeErrorId.set(item.id);
      },
    });
  }

  private load(reset: boolean): void {
    if (reset) {
      this.page = 1;
      this.hasError.set(false);
      this.isLoading.set(true);
    } else {
      this.isLoadingMore.set(true);
    }

    const domain = this.selectedDomain() || undefined;
    this.professionalService.getPublicQA(domain, this.page, PAGE_SIZE).subscribe({
      next: (results) => {
        this.items.update((current) => (reset ? results : [...current, ...results]));
        this.hasMore.set(results.length === PAGE_SIZE);
        this.page += 1;
        this.isLoading.set(false);
        this.isLoadingMore.set(false);
      },
      error: (err) => {
        this.hasError.set(true);
        this.errorKey.set(errorKeyFrom(err));
        this.isLoading.set(false);
        this.isLoadingMore.set(false);
      },
    });
  }
}
