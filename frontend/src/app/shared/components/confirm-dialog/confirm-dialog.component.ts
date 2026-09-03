import { Component, input, output, signal } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';

/**
 * Generic confirmation dialog.
 *
 * **The text inputs take display text, not translation keys.** A caller passes
 * text it has already translated in its own template, which keeps this
 * component free of any single feature's key namespace:
 *
 * ```html
 * <app-confirm-dialog [title]="'forum.delete_post.title' | transloco" ... />
 * ```
 *
 * Each text input defaults to empty, and the template falls back to a generic
 * prompt from `shared.confirm_dialog.*` in the active language — that is where
 * the Hebrew literals that used to be the input defaults now live.
 */
@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [TranslocoPipe],
  templateUrl: './confirm-dialog.component.html',
  styleUrl: './confirm-dialog.component.scss',
})
export class ConfirmDialogComponent {
  /** Heading. Falls back to a generic "are you sure?" prompt. */
  title = input<string>('');
  message = input<string>('');
  /** Confirm button text. Falls back to a generic "confirm". */
  confirmText = input<string>('');
  /** Cancel button text. Falls back to a generic "cancel". */
  cancelText = input<string>('');
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
