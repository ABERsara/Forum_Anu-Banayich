import { Component, input } from '@angular/core';

@Component({
  selector: 'app-error-display',
  standalone: true,
  template: `
    @if (message()) {
      <div class="error-display" role="alert">
        <span class="error-icon" aria-hidden="true">⚠</span>
        <span>{{ message() }}</span>
      </div>
    }
  `,
  styleUrl: './error-display.component.scss',
})
export class ErrorDisplayComponent {
  /** The failure to show — already translated by the caller. */
  message = input<string>('');
}
