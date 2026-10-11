/**
 * One audit log entry, in full — the dialog a row of the audit log opens onto
 * (ABF-153).
 *
 * The list shows who, what, when and to which entity. This shows the rest of
 * the record, and above all `details`: the context the logging service
 * attached, which the list deliberately leaves out because a JSON object does
 * not fit in a table cell.
 *
 * It fetches its own entry (`GET /admin/audit-log/{id}`) rather than being
 * handed the row, so it needs nothing but an id and depends on nothing about
 * the list page that happens to be on screen. A request still in flight when
 * the dialog closes is cancelled with it.
 *
 * `details` is laid out as indented JSON — `JSON.stringify(details, null, 2)`
 * over the object the API sent — never as the one-line, backslash-escaped
 * string a JSON value turns into when it is printed as text. It sits in a
 * `<pre dir="ltr">`: JSON is Latin punctuation read left to right, and in an
 * RTL page the braces and commas would otherwise be reordered around it.
 *
 * Like the list, it never shows an IP address. The API does not send one,
 * and this component names only the fields of `AuditLogEntry`.
 *
 * A modal in the full sense, not only in look: `role="dialog"` with
 * `aria-modal`, focus moved onto it when it opens, Tab kept inside it,
 * Escape and the backdrop close it. Handing focus back to whatever opened it
 * is the opener's job — only it knows which row that was.
 */

import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  OnInit,
  computed,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslocoPipe } from '@jsverse/transloco';

import { LabelService } from '../../../../core/i18n/label.service';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../../core/i18n/screen-error';
import { AuditLogEntry } from '../../../../core/models';
import { AdminService } from '../../../../core/services/admin.service';
import { ErrorDisplayComponent } from '../../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../../shared/components/loading-spinner/loading-spinner.component';
import { auditActionLabel, auditOccurredAt } from '../audit-log.util';

/** What Tab can land on inside the dialog. */
const FOCUSABLE = 'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

@Component({
  selector: 'app-audit-log-entry-dialog',
  standalone: true,
  imports: [DatePipe, TranslocoPipe, ErrorDisplayComponent, LoadingSpinnerComponent],
  templateUrl: './audit-log-entry-dialog.component.html',
  styleUrl: './audit-log-entry-dialog.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuditLogEntryDialogComponent implements OnInit, AfterViewInit {
  private readonly adminService = inject(AdminService);
  private readonly labels = inject(LabelService);
  private readonly destroyRef = inject(DestroyRef);

  /** The entry to show. The dialog fetches it itself. */
  readonly entryId = input.required<string>();

  /** Escape, the close button or the backdrop. The opener removes the dialog. */
  readonly closed = output<void>();

  readonly entry = signal<AuditLogEntry | null>(null);
  readonly isLoading = signal(false);
  /** A key of ours, or the sentence the API sent (ABF-129). */
  readonly loadError = signal<ScreenError>(NO_ERROR);

  readonly hasLoadError = computed(
    () => this.loadError().key !== '' || this.loadError().text !== '',
  );

  /**
   * `details` as indented JSON, or `''` when there is nothing to show.
   *
   * An empty object counts as nothing: `{}` in a code block reads as a
   * rendering fault, where "no details were recorded" is what it means.
   */
  readonly detailsJson = computed(() => {
    const details = this.entry()?.details;
    return details && Object.keys(details).length > 0 ? JSON.stringify(details, null, 2) : '';
  });

  private readonly panel = viewChild.required<ElementRef<HTMLElement>>('panel');
  private readonly closeButton = viewChild.required<ElementRef<HTMLButtonElement>>('closeButton');

  ngOnInit(): void {
    this.load();
  }

  /**
   * Focus onto the close button, the one control that is there in every
   * state — loading, failed and loaded alike. A screen reader announces the
   * dialog's name as focus enters it, and Escape works from the first moment.
   */
  ngAfterViewInit(): void {
    this.closeButton().nativeElement.focus();
  }

  /** Try the request again, after a failure. */
  retry(): void {
    this.load();
  }

  close(): void {
    this.closed.emit();
  }

  /**
   * A click on the dimmed backdrop closes; a click that started on the panel
   * and bubbled up to it does not — otherwise selecting text in `details`
   * would dismiss the record being read.
   */
  onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      this.close();
    }
  }

  /** Escape closes, and Tab cycles inside the panel instead of leaving it. */
  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      this.close();
      return;
    }
    if (event.key !== 'Tab') {
      return;
    }

    const focusable = [...this.panel().nativeElement.querySelectorAll<HTMLElement>(FOCUSABLE)];
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

  /** The action, exactly as the list's row named it — see `../audit-log.util.ts`. */
  actionLabel(entry: AuditLogEntry): string {
    return auditActionLabel(entry, this.labels);
  }

  /** The timestamp as an instant, as the list reads it — see `../audit-log.util.ts`. */
  occurredAt(entry: AuditLogEntry): string {
    return auditOccurredAt(entry);
  }

  private load(): void {
    this.isLoading.set(true);
    this.loadError.set(NO_ERROR);

    this.adminService
      .getAuditLogEntry(this.entryId())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (entry) => {
          this.entry.set(entry);
          this.isLoading.set(false);
        },
        error: (err: unknown) => {
          this.entry.set(null);
          this.loadError.set(screenErrorFrom(err, 'admin.errors.load_audit_log_entry_failed'));
          this.isLoading.set(false);
        },
      });
  }
}
