import { Component, input, output } from '@angular/core';

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

  confirmed = output<void>();
  cancelled = output<void>();
}

