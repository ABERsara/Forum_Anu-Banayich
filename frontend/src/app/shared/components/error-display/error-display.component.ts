import { Component, input } from '@angular/core';

@Component({
  selector: 'app-error-display',
  standalone: true,
  template: `
    @if (message()) {
      <div class="error-display" role="alert" dir="rtl">
        <span class="error-icon" aria-hidden="true">⚠</span>
        <span>{{ message() }}</span>
      </div>
    }
  `,
  styleUrl: './error-display.component.scss',
})
export class ErrorDisplayComponent {
  message = input<string>('');
}
