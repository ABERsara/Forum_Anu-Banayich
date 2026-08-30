import { Component, input } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';

@Component({
  selector: 'app-loading-spinner',
  imports: [TranslocoPipe],
  template: `
    <div class="spinner-wrapper">
      <span
        class="spinner"
        [class]="'spinner--' + size()"
        [attr.aria-label]="'common.loading' | transloco"
      ></span>
      @if (message()) {
        <p class="spinner-message">{{ message() }}</p>
      }
    </div>
  `,
  styleUrl: './loading-spinner.component.scss',
})
export class LoadingSpinnerComponent {
  size = input<'sm' | 'md' | 'lg'>('md');
  /** Optional caption under the spinner — already translated by the caller. */
  message = input<string>('');
}
