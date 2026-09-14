/**
 * The report control, and the dialog behind it.
 *
 * One component for every kind of reportable content. ABF-112 added private
 * messages to it rather than forking a second dialog, so a rule that matters
 * — a reason has to be chosen, and what a report exposes is said before it is
 * sent — holds everywhere reporting exists instead of on whichever screen was
 * written last.
 *
 * What ABF-112 changed for the screens that already used it:
 *
 *   - no reason is preselected. It used to open on "harassment", so anyone who
 *     just pressed send filed the gravest reason available without choosing
 *     it. §7.1 says the user picks a reason, and now she has to.
 *   - the dialog is a real dialog: labelled, modal to assistive technology,
 *     opened with focus inside it, closed by Escape, and it gives focus back
 *     to the control that opened it.
 */

import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  ElementRef,
  ViewChild,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';

import { REPORT_REASON_LABELS, ReportReason, ReportTargetType } from '../../../core/constants';
import { ReportService } from '../../../core/services/report.service';
import { ErrorDisplayComponent } from '../error-display/error-display.component';

/**
 * What each content type has to say before a report is confirmed, or null
 * when there is nothing extra to warn about.
 *
 * Keyed by content type rather than passed in by the caller: the disclosure is
 * a property of what reporting that content does, so a screen cannot add a
 * reporting control and forget the warning that belongs with it.
 *
 * A forum post has no entry on purpose — it is already visible to a whole
 * cell, so "a moderator will read this" reveals nothing the author did not
 * publish. A private message is visible to two people, and handing one over is
 * the consent §5.3 is built on.
 */
const DISCLOSURE_KEYS: Partial<Record<ReportTargetType, string>> = {
  [ReportTargetType.DIRECT_MESSAGE]: 'shared.report.disclosure_direct_message',
};

@Component({
  selector: 'app-report-button',
  standalone: true,
  imports: [TranslocoPipe, ErrorDisplayComponent],
  templateUrl: './report-button.component.html',
  styleUrl: './report-button.component.scss',
})
export class ReportButtonComponent {
  private readonly reportService = inject(ReportService);

  contentType = input.required<ReportTargetType>();
  contentId = input.required<string>();

  /**
   * Accessible name for the control, already translated.
   *
   * A conversation puts one of these on every received message, and fifty
   * buttons all called "report" are fifty buttons a screen-reader user cannot
   * tell apart. Screens with a single report control leave it unset and keep
   * the visible label as the name.
   */
  triggerLabel = input<string | null>(null);

  /** The server says this viewer has already reported this content. */
  alreadyReported = input(false);

  /** Emitted once a report has actually been stored. */
  reported = output<void>();

  @ViewChild('dialog') private dialog?: ElementRef<HTMLElement>;
  @ViewChild('firstField') private firstField?: ElementRef<HTMLSelectElement>;

  showDialog = signal(false);

  /**
   * Null until the user picks one — which is the whole of "no report without
   * a reason" on this side of the wire. The server enforces it again; a
   * dialog is not a permission check.
   */
  reason = signal<ReportReason | null>(null);
  description = signal('');
  isSubmitting = signal(false);
  isSubmitted = signal(false);

  /**
   * The failure to show, as a translation key rather than as text.
   *
   * The template runs it through the `transloco` pipe, so a message that is on
   * screen when the reader switches language switches with it. Resolving it
   * here instead would freeze it in the language it was raised in.
   */
  errorKey = signal<string | null>(null);

  readonly reasonOptions = Object.values(ReportReason);
  readonly reasonLabels = REPORT_REASON_LABELS;

  /** Either this session filed one, or the server said an earlier one did. */
  hasReported = computed(() => this.isSubmitted() || this.alreadyReported());

  disclosureKey = computed(() => DISCLOSURE_KEYS[this.contentType()] ?? null);

  /**
   * Prefix for the ids inside the dialog, derived from the content it is
   * about.
   *
   * A conversation renders one of these per message, so a fixed id would put
   * fifty `id="report-reason"` attributes on the page and every `for=` would
   * point at whichever the browser found first — a label attached to the
   * wrong control, which is worse than no label at all.
   */
  fieldId = computed(() => `report-${this.contentId()}`);

  canSubmit = computed(() => this.reason() !== null && !this.isSubmitting());

  /** The control to hand focus back to when the dialog closes. */
  private opener: HTMLElement | null = null;

  onOpenClick(event: Event): void {
    this.opener = event.currentTarget as HTMLElement;
    this.errorKey.set(null);
    this.reason.set(null);
    this.description.set('');
    this.showDialog.set(true);
    // After the dialog exists in the DOM, not before — and on the reason
    // field rather than the dialog box, because choosing a reason is the one
    // thing that has to happen before this dialog can do anything.
    queueMicrotask(() => this.firstField?.nativeElement.focus());
  }

  onCancel(): void {
    this.showDialog.set(false);
    this.opener?.focus();
  }

  /**
   * Escape closes it — WCAG 2.1.2, and the behaviour anyone who has met a
   * dialog before will try first.
   */
  onDialogKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.stopPropagation();
      this.onCancel();
      return;
    }
    if (event.key === 'Tab') this.trapTab(event);
  }

  /**
   * Keep Tab inside the dialog.
   *
   * `aria-modal` tells assistive technology the rest of the page is inert; it
   * does not stop the browser tabbing into it. Without this, Tab from the last
   * control lands on the page behind a dialog a screen reader has just
   * described as modal, and there is no obvious way back.
   */
  private trapTab(event: KeyboardEvent): void {
    const focusable = this.focusableControls();
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;

    if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  private focusableControls(): HTMLElement[] {
    const root = this.dialog?.nativeElement;
    if (!root) return [];
    return Array.from(
      root.querySelectorAll<HTMLElement>('button, select, textarea, [href], input'),
    ).filter((element) => !element.hasAttribute('disabled'));
  }

  onReasonChange(value: string): void {
    this.reason.set(value === '' ? null : (value as ReportReason));
  }

  onDescriptionChange(value: string): void {
    this.description.set(value);
  }

  onSubmit(): void {
    const reason = this.reason();
    // Not only the disabled button: a form can be submitted by keyboard
    // before the guard's own state has caught up, and this is the criterion
    // the whole dialog exists to satisfy.
    if (reason === null || this.isSubmitting()) return;

    this.isSubmitting.set(true);
    this.errorKey.set(null);
    this.reportService
      .fileReport({
        target_type: this.contentType(),
        target_id: this.contentId(),
        reason,
        description: this.description().trim() || undefined,
      })
      .subscribe({
        next: () => {
          this.isSubmitting.set(false);
          this.showDialog.set(false);
          this.isSubmitted.set(true);
          this.opener?.focus();
          this.reported.emit();
        },
        error: (err: HttpErrorResponse) => {
          this.isSubmitting.set(false);
          this.errorKey.set(
            err.status === 409 ? 'shared.report.error_duplicate' : 'shared.report.error_generic',
          );
        },
      });
  }
}
