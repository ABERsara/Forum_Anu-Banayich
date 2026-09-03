import { Component, input, output, signal } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';

export interface SuspendDialogResult {
  hours: number;
  reason: string;
}

/**
 * Suspension dialog: how many hours, and why.
 *
 * Text inputs take display text, not translation keys — see
 * `confirm-dialog.component.ts` for the reasoning. The hours/reason field
 * labels belong to this dialog rather than to a caller, so those stay here as
 * keys under `shared.suspend_dialog.*`.
 */
@Component({
  selector: 'app-suspend-dialog',
  standalone: true,
  imports: [TranslocoPipe],
  templateUrl: './suspend-dialog.component.html',
  styleUrl: './suspend-dialog.component.scss',
})
export class SuspendDialogComponent {
  /** Heading. Falls back to a generic "suspend user". */
  title = input<string>('');
  message = input<string>('');
  /** Confirm button text. Falls back to a generic "suspend". */
  confirmText = input<string>('');
  /** Cancel button text. Falls back to a generic "cancel". */
  cancelText = input<string>('');

  hoursValue = signal(48);
  reasonValue = signal('');

  /** Emits { hours, reason } (reason trimmed) when confirmed. */
  confirmed = output<SuspendDialogResult>();
  cancelled = output<void>();

  // Validation (min 1 hour, min 5 chars) is hardcoded to match the backend's
  // SuspendUserRequest constraints, not exposed as inputs like confirm-dialog's
  // inputMinLength. Revisit only if a second consumer needs different bounds.
  get isConfirmDisabled(): boolean {
    return this.hoursValue() <= 0 || this.reasonValue().trim().length < 5;
  }

  onHoursChange(value: string): void {
    this.hoursValue.set(Number(value));
  }

  onReasonChange(value: string): void {
    this.reasonValue.set(value);
  }

  onConfirm(): void {
    if (this.isConfirmDisabled) {
      return;
    }
    this.confirmed.emit({ hours: this.hoursValue(), reason: this.reasonValue().trim() });
  }
}
