/**
 * One report, on a screen of its own (SPEC §7.3).
 *
 * The queue shows a preview of each report so a moderator can work through
 * many of them; this screen is the other half of that — the reported content
 * in full, the context the decision rests on, and the decision itself.
 *
 * Reached from a row of the queue and scoped server-side: `GET
 * /moderator/reports/{id}` answers 403 for a report outside this moderator's
 * cells and 404 for one that does not exist, so an id typed into the address
 * bar gets no further than the queue would have. The `roleGuard` on the route
 * is what keeps the wrong role out; this screen assumes neither.
 *
 * **A private message is read here, and the read is audited.** `getReport()`
 * is the one call that ever returns a DIRECT_MESSAGE report's plaintext, and
 * the server records the read as a view (ABF-113, spec §9.1/§9.3). The queue
 * asks for it behind an explicit "view content" button because a row does not
 * otherwise need it; this screen cannot, since the same call is where its
 * reason, its dates and its decision come from. Opening the page *is* the
 * read — so the page says so, rather than letting a moderator find out from
 * the audit log.
 *
 * **Two requests, and why.** The report carries the content and the report's
 * own fields. It does not carry the reported member's name or what was decided
 * about her before — that is `UserModerationCard`, which the user card screen
 * already loads from an endpoint scoped to the same cells. It is fetched once
 * the report names the member, and a card that never arrives costs this screen
 * a name and three counts and nothing else: a report a moderator can read and
 * decide is worth more than a screen that refuses to draw because a second
 * request failed.
 *
 * **Which keys the copy comes from.** A label that names a field of a payload
 * belongs to that payload: the report's own fields render through
 * `moderator.reports.*` and the card's counts through `moderator.user_card.*`,
 * which is where the two screens that own those payloads already put them. A
 * private copy of "סיבת הדיווח" here would be the duplication CONTRIBUTING §6
 * forbids, and the first place the two screens could drift apart. Only this
 * screen's own voice — its title, its sections, what it says about the
 * reporter — sits under `moderator.report_detail.*`.
 *
 * Important:
 *   - The reporter is never named. The moderator decides on the content, and
 *     the API sends an opaque id that this screen deliberately does not show.
 *   - Deciding is the same two-step action as in the queue, down to the copy
 *     in the dialog: either button opens a confirmation that will not submit
 *     without a note, and the note is the only record of why once the content
 *     is gone.
 */

import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { ReportWithContent, UserModerationCard } from '../../../core/models';
import {
  POST_STATUS_LABELS,
  REPORT_DECISION_LABELS,
  REPORT_REASON_LABELS,
  ReportDecision,
  ReportTargetType,
} from '../../../core/constants';
import { LabelService } from '../../../core/i18n/label.service';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { ReportService } from '../../../core/services/report.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

/** Matches the note length the backend enforces on ReportDecideRequest. */
const MIN_NOTE_LENGTH = 5;

/**
 * Stands in for a field the report carries nothing in — the description the
 * reporter left empty, or the note on a decision taken before notes were
 * required.
 *
 * A dash is a glyph, not copy: it reads the same in both languages and is
 * Bidi-neutral, so it stays out of the translation files — the same call the
 * queue's description dash got in ABF-134.
 */
const EMPTY_VALUE = '–';

@Component({
  selector: 'app-moderator-report-detail',
  standalone: true,
  imports: [
    DatePipe,
    RouterLink,
    TranslocoPipe,
    ConfirmDialogComponent,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
  templateUrl: './report-detail.component.html',
  styleUrl: './report-detail.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ModeratorReportDetailComponent implements OnInit {
  /** Bound from the :id route parameter (withComponentInputBinding). */
  readonly id = input.required<string>();

  private readonly reportService = inject(ReportService);
  private readonly labels = inject(LabelService);

  readonly report = signal<ReportWithContent | null>(null);
  readonly isLoading = signal(false);
  readonly hasError = signal(false);

  /**
   * The reported member's card: her name for the heading of this screen, and
   * the reports about her that were already decided. Null until it arrives,
   * and null for good if it does not — see `cardError`.
   */
  readonly card = signal<UserModerationCard | null>(null);
  readonly isCardLoading = signal(false);
  readonly cardError = signal(false);

  /** The decision awaiting confirmation; null when the dialog is closed. */
  readonly pendingDecision = signal<ReportDecision | null>(null);
  /** Held as a key or a server sentence, never as translated text (ABF-132). */
  readonly actionError = signal<ScreenError>(NO_ERROR);

  readonly reasonLabels = REPORT_REASON_LABELS;
  readonly decisionLabels = REPORT_DECISION_LABELS;
  readonly postStatusLabels = POST_STATUS_LABELS;
  readonly targetTypes = ReportTargetType;
  readonly decisions = ReportDecision;
  readonly minNoteLength = MIN_NOTE_LENGTH;
  readonly emptyValue = EMPTY_VALUE;

  /**
   * Only a report still waiting is decided here. The server answers 409 to a
   * second decision on the same report, and a button that was going to be
   * refused is worse than no button — this screen is also where a report that
   * has already been decided is read back.
   */
  readonly isPending = computed(() => this.report()?.decision === ReportDecision.PENDING);

  /** A private message was read to draw this page — see the class comment. */
  readonly isDirectMessage = computed(
    () => this.report()?.target_type === ReportTargetType.DIRECT_MESSAGE,
  );

  /**
   * What to call the thing that was reported.
   *
   * A DIRECT_MESSAGE report has no title at all, so it takes a generic one;
   * a FORUM_POST report has the title its author wrote, unless the row behind
   * it is gone. Both keys are the queue's — it answers the same question one
   * row at a time, and two screens naming the same thing differently is how
   * they start to drift (ABF-113 established both).
   *
   * Resolved here rather than in the template because it is also a *parameter*
   * of two translated `aria-label`s, and a `| transloco` result cannot be the
   * argument of a second one. Through `LabelService`, so it still follows a
   * language switch — `translate()` would freeze it (CONTRIBUTING §6).
   */
  readonly reportTitle = computed(() => {
    const report = this.report();
    if (!report) {
      return '';
    }
    if (report.target_type === ReportTargetType.FORUM_POST) {
      return report.content_title ?? this.labels.label('moderator.reports.content_gone_title');
    }
    return this.labels.label('moderator.reports.direct_message_title');
  });

  /** The reported member's name, once her card has arrived. */
  readonly reportedUserName = computed(() => {
    const card = this.card();
    return card ? `${card.first_name} ${card.last_name}` : '';
  });

  /**
   * What the screen says about who filed the report.
   *
   * Never a name and never the id: the moderator decides on the content, which
   * is why the API sends an opaque id here in the first place. The one fact
   * worth telling apart is a report whose reporter has since closed her
   * account — §9.4 keeps the report for five years without the person, and an
   * empty `reporter_id` is what that looks like, rather than a report that
   * arrived with nobody behind it.
   */
  readonly reporterKey = computed(() =>
    this.report()?.reporter_id
      ? 'moderator.report_detail.reporter_withheld'
      : 'moderator.report_detail.reporter_anonymized',
  );

  ngOnInit(): void {
    this.loadReport();
  }

  // ---------------------------------------------------------------------------
  // Loading
  // ---------------------------------------------------------------------------

  private loadReport(): void {
    this.isLoading.set(true);
    this.hasError.set(false);
    this.reportService.getReport(this.id()).subscribe({
      next: (report) => {
        this.report.set(report);
        this.isLoading.set(false);
        this.loadCard(report.reported_user_id);
      },
      error: () => {
        this.hasError.set(true);
        this.isLoading.set(false);
      },
    });
  }

  /**
   * The reported member's card, which is where her name and the decisions
   * already taken about her come from.
   *
   * Its failure is kept apart from the report's: this sets `cardError` and
   * leaves `hasError` alone, so one section says it is unavailable and the
   * report stays readable and decidable.
   */
  private loadCard(userId: string): void {
    this.isCardLoading.set(true);
    this.cardError.set(false);
    this.reportService.getUserCard(userId).subscribe({
      next: (card) => {
        this.card.set(card);
        this.isCardLoading.set(false);
      },
      error: () => {
        this.cardError.set(true);
        this.isCardLoading.set(false);
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Deciding
  // ---------------------------------------------------------------------------

  decide(decision: ReportDecision): void {
    this.actionError.set(NO_ERROR);
    this.pendingDecision.set(decision);
  }

  cancelDecision(): void {
    this.pendingDecision.set(null);
  }

  confirmDecision(note: string): void {
    const decision = this.pendingDecision();
    if (!decision) {
      return;
    }

    this.reportService.decideReport(this.id(), { decision, note }).subscribe({
      next: () => {
        this.pendingDecision.set(null);
        // The reply carries the report's own fields and not the content's, and
        // the decision changed both — VALID removes what was reported, INVALID
        // puts a post the two-report rule auto-hid back on the forum. What the
        // content ends up as is the server's rule and not this screen's, so the
        // report is loaded again rather than patched from the reply. That
        // reload brings the card with it, because a decision is exactly what
        // moves the counts below.
        //
        // On a DIRECT_MESSAGE report that second load is a second audited read
        // (ABF-113) — by the moderator who has just decided on the message she
        // was reading, which is what the audit log should say happened.
        this.loadReport();
      },
      error: (err: unknown) => {
        this.actionError.set(screenErrorFrom(err, 'moderator.errors.decide_failed'));
        this.pendingDecision.set(null);
      },
    });
  }

  /**
   * What the confirmation says the decision is about to do — the *key*, piped
   * by the template. The dialog is a shared component and takes finished text,
   * so the caller is where the pipe belongs (CONTRIBUTING §6, ABF-128).
   *
   * The keys are the queue's own: the sentence that warns a moderator she is
   * about to delete a bereaved member's post should not depend on which screen
   * she pressed the button from.
   */
  confirmTitleKey(decision: ReportDecision): string {
    return decision === ReportDecision.VALID
      ? 'moderator.reports.confirm_valid_title'
      : 'moderator.reports.confirm_invalid_title';
  }

  confirmMessageKey(decision: ReportDecision): string {
    return decision === ReportDecision.VALID
      ? 'moderator.reports.confirm_valid_message'
      : 'moderator.reports.confirm_invalid_message';
  }
}
