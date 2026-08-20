import { Component, input, output } from '@angular/core';
import { LoadingSpinnerComponent } from '../loading-spinner/loading-spinner.component';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

@Component({
  selector: 'app-button',
  templateUrl: './button.component.html',
  imports: [LoadingSpinnerComponent],
  styleUrl: './button.component.scss',
})
export class ButtonComponent {
  variant = input<ButtonVariant>('primary');
  size = input<ButtonSize>('md');
  disabled = input(false);
  loading = input(false);
  type = input<'button' | 'submit' | 'reset'>('button');

  /**
   * Accessible name, for a button whose own text does not identify it
   * (CONTRIBUTING §5). "אישור" repeated down a list says nothing about *whose*
   * request is being approved; the label does.
   *
   * The three aria inputs below land on the inner <button>, not on the
   * <app-button> host — an aria attribute on a wrapper the screen reader does
   * not treat as the control is an attribute nobody hears. Each defaults to
   * null, which renders no attribute at all.
   */
  ariaLabel = input<string | null>(null);
  /** Whether the panel this button discloses is open. Null on a plain button. */
  ariaExpanded = input<boolean | null>(null);
  /** id of the element `ariaExpanded` refers to. */
  ariaControls = input<string | null>(null);

  clicked = output<MouseEvent>();

  get classes(): string {
    return ['btn', `btn--${this.variant()}`, `btn--${this.size()}`].join(' ');
  }
}
