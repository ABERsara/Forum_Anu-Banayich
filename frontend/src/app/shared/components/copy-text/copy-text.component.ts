import {
  ChangeDetectionStrategy,
  Component,
  OnDestroy,
  input,
  output,
  signal,
} from '@angular/core';

/**
 * Copies a text string to the clipboard and shows brief visual confirmation.
 *
 * Usage:
 *   <app-copy-text [text]="someValue" />
 *   <app-copy-text [text]="someValue" label="Copy ID" successLabel="Copied!" />
 *
 * Architecture notes (reference for all shared components):
 * - Standalone, no NgModule
 * - signal-based inputs (input() / output()) — not @Input / @Output
 * - ChangeDetectionStrategy.OnPush — required for all shared/ components
 * - No service injection — receives everything via input(), emits via output()
 * - OnDestroy clears the timer to avoid memory leaks
 */
@Component({
  selector: 'app-copy-text',
  templateUrl: './copy-text.component.html',
  styleUrl: './copy-text.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CopyTextComponent implements OnDestroy {
  /** The string that will be written to the clipboard. */
  text = input.required<string>();

  /** Button label before the user copies. */
  label = input('העתק');

  /** Button label shown briefly after a successful copy. */
  successLabel = input('הועתק!');

  /** Emits once per successful clipboard write. */
  copied = output<void>();

  readonly isCopied = signal(false);

  private resetTimer: ReturnType<typeof setTimeout> | null = null;

  async copy(): Promise<void> {
    if (!navigator.clipboard) return;

    try {
      await navigator.clipboard.writeText(this.text());
    } catch {
      return;
    }

    this.copied.emit();
    this.isCopied.set(true);

    if (this.resetTimer) clearTimeout(this.resetTimer);
    this.resetTimer = setTimeout(() => this.isCopied.set(false), 2000);
  }

  ngOnDestroy(): void {
    if (this.resetTimer) clearTimeout(this.resetTimer);
  }
}
