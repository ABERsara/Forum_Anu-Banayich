import { Component, input, output, signal } from '@angular/core';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  templateUrl: './confirm-dialog.component.html',
  styleUrl: './confirm-dialog.component.scss',
})
export class ConfirmDialogComponent {
  title = input<string>('האם לאשר?');
  message = input<string>('');
  confirmText = input<string>('אישור');
  cancelText = input<string>('ביטול');
  isDestructive = input<boolean>(false);

  /** When true, renders a required textarea and blocks confirm until it reaches inputMinLength. */
  requireInput = input<boolean>(false);
  inputLabel = input<string>('');
  inputPlaceholder = input<string>('');
  inputMinLength = input<number>(0);

  inputValue = signal('');

  /** Emits the trimmed textarea value (empty string when requireInput is false). */
  confirmed = output<string>();
  cancelled = output<void>();

  get isConfirmDisabled(): boolean {
    return this.requireInput() && this.inputValue().trim().length < this.inputMinLength();
  }

  onInputChange(value: string): void {
    this.inputValue.set(value);
  }

  onConfirm(): void {
    if (this.isConfirmDisabled) {
      return;
    }
    this.confirmed.emit(this.inputValue().trim());
  }
}
