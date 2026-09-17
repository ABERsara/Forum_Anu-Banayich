/**
 * Audit log viewer — admin only (SPEC §9.3, ABF-152).
 *
 * A real table over `GET /admin/audit-log`: four columns (who / what / when /
 * entity), a filter panel, a sortable `when` header, and a pager. Nothing is
 * filtered, sorted or sliced here — every one of those is a parameter on the
 * request, because the table is append-only, kept for seven years, and far
 * past the size at which a browser can hold it.
 *
 * Two shapes of state, deliberately kept apart:
 *
 *   `draft`   — what is currently typed into the filter boxes.
 *   `applied` — what the rows on screen were actually fetched with.
 *
 * Typing does not refetch. The separation is what lets the empty state say
 * *which* emptiness it means ("no entries match the filters you chose" rather
 * than "the log is empty") without that message flickering between the
 * keystroke and the request.
 *
 * The one thing this screen never shows is the actor's IP address. The API
 * does not send it, under any parameter, and the decision recorded on this
 * ticket is that no screen ever will.
 *
 * `details` is fetched — it is part of the frozen contract — and deliberately
 * not rendered: the single-entry view is Task 2, and a JSON blob squeezed into
 * a list row is the thing that view exists to do properly.
 */

import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { AUDIT_ACTION_LABELS, AuditAction, SortDirection } from '../../../core/constants';
import { LabelService } from '../../../core/i18n/label.service';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { AuditLogEntry, AuditLogQuery } from '../../../core/models';
import { ReportService } from '../../../core/services/report.service';
import { utcIso } from '../../../core/utils/utc-date.util';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

/** Matches the server's default, so page 1 asks for what it would get anyway. */
const PAGE_SIZE = 50;

/** The filter boxes, as text. Empty string means "not filtering by this". */
interface Filters {
  actorId: string;
  actionType: string;
  entityType: string;
  entityId: string;
  dateFrom: string;
  dateTo: string;
}

const NO_FILTERS: Filters = {
  actorId: '',
  actionType: '',
  entityType: '',
  entityId: '',
  dateFrom: '',
  dateTo: '',
};

/** Which box a change came from, so one handler can serve all six. */
type FilterField = keyof Filters;

@Component({
  selector: 'app-audit-log',
  standalone: true,
  imports: [DatePipe, RouterLink, TranslocoPipe, ErrorDisplayComponent, LoadingSpinnerComponent],
  templateUrl: './audit-log.component.html',
  styleUrl: './audit-log.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuditLogComponent implements OnInit {
  private readonly reportService = inject(ReportService);
  private readonly labels = inject(LabelService);

  readonly entries = signal<AuditLogEntry[]>([]);
  readonly totalCount = signal(0);
  readonly page = signal(1);
  readonly isLoading = signal(false);
  /** A key of ours, or the sentence the API sent (ABF-129). */
  readonly loadError = signal<ScreenError>(NO_ERROR);

  readonly draft = signal<Filters>(NO_FILTERS);
  readonly applied = signal<Filters>(NO_FILTERS);
  readonly direction = signal<SortDirection>(SortDirection.DESC);

  readonly pageSize = PAGE_SIZE;
  readonly directions = SortDirection;
  /** Every action the filter dropdown offers, in the enum's own order. */
  readonly actionTypes = Object.values(AuditAction);
  readonly actionLabels = AUDIT_ACTION_LABELS;

  readonly pageCount = computed(() => Math.max(1, Math.ceil(this.totalCount() / this.pageSize)));
  readonly hasPreviousPage = computed(() => this.page() > 1);
  readonly hasNextPage = computed(() => this.page() < this.pageCount());

  /** Whether the rows on screen were narrowed by anything. */
  readonly isFiltered = computed(() => Object.values(this.applied()).some((value) => value !== ''));

  /**
   * Whether the last load failed, either way round.
   *
   * `ScreenError` sets exactly one of its two fields, so "did it fail" is the
   * disjunction — and the template needs it as one question, to keep an empty
   * table from appearing under the error and claiming the log is empty.
   */
  readonly hasLoadError = computed(
    () => this.loadError().key !== '' || this.loadError().text !== '',
  );

  /**
   * What `aria-sort` on the `when` header should say.
   *
   * It is the only sortable column, so this is the whole sort state — and it
   * is `aria-sort` rather than only an arrow glyph because a screen reader
   * reading the header otherwise announces a plain column and gives no hint
   * that the button under it did anything.
   */
  readonly sortState = computed(() =>
    this.direction() === SortDirection.ASC ? 'ascending' : 'descending',
  );

  /**
   * Which response is allowed to land.
   *
   * Every fetch takes a ticket, and a response whose ticket is stale is
   * dropped. Four controls on this screen start a request — apply, clear,
   * the sort header and the pager — and an admin who clicks `next` twice
   * while the first page is still in flight would otherwise be shown
   * whichever response happened to arrive last, with a page number that says
   * something else.
   */
  private latestRequest = 0;

  ngOnInit(): void {
    this.load();
  }

  // ---------------------------------------------------------------------------
  // Filters
  // ---------------------------------------------------------------------------

  /**
   * Record a keystroke. Nothing is fetched until `applyFilters()` — see the
   * class comment on why `draft` and `applied` are two things.
   */
  updateDraft(field: FilterField, value: string): void {
    this.draft.update((current) => ({ ...current, [field]: value }));
  }

  /** The value an `<input>`/`<select>` event carries, for the template. */
  valueOf(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement).value;
  }

  applyFilters(): void {
    this.applied.set(this.draft());
    // Back to page 1: page 4 of the unfiltered log is very unlikely to exist
    // under the new filter, and landing on an empty page reads as "no
    // matches" when in fact there were plenty on page 1.
    this.page.set(1);
    this.load();
  }

  clearFilters(): void {
    this.draft.set(NO_FILTERS);
    this.applied.set(NO_FILTERS);
    this.page.set(1);
    this.load();
  }

  // ---------------------------------------------------------------------------
  // Sorting
  // ---------------------------------------------------------------------------

  /**
   * Flip the `when` column between newest-first and oldest-first.
   *
   * Back to page 1 as well, for a sharper reason than the filters have:
   * reversing the order while staying on page 3 keeps the offset and changes
   * what is under it, so the reader is dropped in the middle of the log at a
   * place that corresponds to nothing they were looking at.
   */
  toggleSort(): void {
    this.direction.update((current) =>
      current === SortDirection.DESC ? SortDirection.ASC : SortDirection.DESC,
    );
    this.page.set(1);
    this.load();
  }

  /**
   * What clicking the header will *do* — which is the opposite of the order
   * on screen now. Announcing the current order here would describe the state
   * `aria-sort` already carries, and leave the button's own purpose unsaid.
   */
  sortActionKey(): string {
    return this.direction() === SortDirection.DESC
      ? 'admin.audit_log.sort_ascending_aria'
      : 'admin.audit_log.sort_descending_aria';
  }

  // ---------------------------------------------------------------------------
  // Paging
  // ---------------------------------------------------------------------------

  goToPreviousPage(): void {
    if (this.hasPreviousPage()) {
      this.page.update((page) => page - 1);
      this.load();
    }
  }

  goToNextPage(): void {
    if (this.hasNextPage()) {
      this.page.update((page) => page + 1);
      this.load();
    }
  }

  // ---------------------------------------------------------------------------
  // Rendering one row
  // ---------------------------------------------------------------------------

  /**
   * The `what` column.
   *
   * Through LabelService rather than the template pipe because of the second
   * branch: an action the server has and this build's `AuditAction` does not
   * has no key to pipe, and the raw wire value is a better cell than a blank
   * one — an audit log that quietly omits what happened is worse than one
   * that says `some_new_action`. The LabelService read is what keeps the
   * first branch following a language switch (CONTRIBUTING §6, ABF-128).
   */
  actionLabel(entry: AuditLogEntry): string {
    const key = this.actionLabels[entry.action_type];
    return key ? this.labels.label(key) : entry.action_type;
  }

  /**
   * The row's timestamp as an *instant*.
   *
   * It arrives as naive UTC — `2026-09-01T12:00:00`, no offset — and the date
   * pipe reads a string without one as a local wall clock, so an admin in
   * Israel would be shown 12:00 for something that happened at 15:00 her
   * time. On an audit log that is not cosmetic: the whole point of the column
   * is to say when, and this is a record that may be read back in a legal
   * proceeding (see `core/utils/utc-date.util.ts`).
   */
  occurredAt(entry: AuditLogEntry): string {
    return utcIso(entry.timestamp);
  }

  // ---------------------------------------------------------------------------
  // Fetching
  // ---------------------------------------------------------------------------

  private load(): void {
    const request = ++this.latestRequest;
    this.isLoading.set(true);
    this.loadError.set(NO_ERROR);

    this.reportService.getAuditLog(this.queryFor(this.applied())).subscribe({
      next: (result) => {
        if (request !== this.latestRequest) {
          return;
        }
        this.entries.set(result.items);
        this.totalCount.set(result.total_count);
        // The server's own answer, not the number that was asked for: a page
        // past the end comes back empty, and the pager has to agree with the
        // rows rather than with the click that produced them.
        this.page.set(result.page);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        if (request !== this.latestRequest) {
          return;
        }
        this.loadError.set(screenErrorFrom(err, 'admin.errors.load_audit_log_failed'));
        // The rows still on screen belong to a query that just failed; the
        // error is the whole answer now.
        this.entries.set([]);
        this.totalCount.set(0);
        this.isLoading.set(false);
      },
    });
  }

  /**
   * The applied filters, the sort and the page, as the service's query object.
   *
   * Empty boxes are left out rather than sent empty — see the service: an
   * `actor_id=` with nothing after it is a filter on the empty string, which
   * matches no row at all.
   */
  private queryFor(filters: Filters): AuditLogQuery {
    const query: AuditLogQuery = {
      direction: this.direction(),
      page: this.page(),
      page_size: this.pageSize,
    };

    if (filters.actorId) query.actor_id = filters.actorId;
    if (filters.actionType) query.action_type = filters.actionType as AuditAction;
    if (filters.entityType) query.entity_type = filters.entityType;
    if (filters.entityId) query.entity_id = filters.entityId;
    if (filters.dateFrom) query.date_from = filters.dateFrom;
    if (filters.dateTo) query.date_to = filters.dateTo;

    return query;
  }
}
