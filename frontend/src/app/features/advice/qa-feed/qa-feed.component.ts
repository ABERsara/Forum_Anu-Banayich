/**
 * Public Q&A feed – shows publicly answered questions.
 *
 * This is the "community knowledge" section (ידע קהילתי).
 */

import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { Subscription } from 'rxjs';

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
  private readonly destroyRef = inject(DestroyRef);

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
  private loadSubscription?: Subscription;

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

  /** The asker's real name if they opted in when asking, otherwise their anonymized alias. */
  askerName(item: PublicQA): string {
    return item.asker ? `${item.asker.first_name} ${item.asker.last_name}` : item.asker_alias;
  }

  /** The answering professional's name — always shown, null only for the theoretical
   *  case of a general/domain question that was never actually targeted at anyone
   *  (unreachable from the current UI, which always asks a specific professional). */
  professionalName(item: PublicQA): string | null {
    return item.professional
      ? `${item.professional.first_name} ${item.professional.last_name}`
      : null;
  }

  toggleLike(item: PublicQA): void {
    this.likeErrorId.set(null);
    this.professionalService
      .toggleLike(item.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
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
    // A domain change while a previous request is still in flight must not
    // let a late, now-stale response overwrite the newer one — cancel it.
    this.loadSubscription?.unsubscribe();

    if (reset) {
      this.page = 1;
      this.hasError.set(false);
      this.isLoading.set(true);
    } else {
      this.isLoadingMore.set(true);
    }

    const domain = this.selectedDomain() || undefined;
    this.loadSubscription = this.professionalService
      .getPublicQA(domain, this.page, PAGE_SIZE)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (results) => {
          this.items.update((current) => (reset ? results : [...current, ...results]));
          // A full page might still be the last one (total count divides
          // evenly by PAGE_SIZE) — that shows "load more" for one extra
          // request that comes back empty, a known, accepted tradeoff rather
          // than changing the endpoint to return an explicit has_more flag.
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
