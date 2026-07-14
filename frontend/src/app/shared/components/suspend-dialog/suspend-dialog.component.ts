import { Component, input, output, signal } from '@angular/core';

export interface SuspendDialogResult {
  hours: number;
  reason: string;
}

@Component({
  selector: 'app-suspend-dialog',
  standalone: true,
  templateUrl: './suspend-dialog.component.html',
  styleUrl: './suspend-dialog.component.scss',
})
export class SuspendDialogComponent {
  title = input<string>('השעיית משתמש');
  message = input<string>('');
  confirmText = input<string>('השעה');
  cancelText = input<string>('ביטול');

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
