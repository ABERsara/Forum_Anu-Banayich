import { Component, DestroyRef, inject, input, output } from '@angular/core';
import { TranslocoPipe, TranslocoService } from '@jsverse/transloco';

@Component({
  selector: 'app-file-upload',
  standalone: true,
  imports: [TranslocoPipe],
  templateUrl: './file-upload.component.html',
  styleUrl: './file-upload.component.scss',
})
export class FileUploadComponent {
  accept = input<string>('image/*,.pdf');
  maxSizeMb = input<number>(5);
  /**
   * Button text — already translated by the caller. Falls back to a generic
   * "choose file" in the active language. See `confirm-dialog.component.ts`.
   */
  label = input<string>('');
  ariaLabel = input<string>('');
  variant = input<'default' | 'primary'>('default');

  fileSelected = output<File>();
  /**
   * The size complaint, as text.
   *
   * The caller owns where this message is shown, so it is resolved here rather
   * than emitted as a key — the output contract stays a plain string. The one
   * consequence: a message already on screen keeps the language it was raised
   * in until the next file is picked.
   */
  validationError = output<string>();

  previewUrl: string | null = null;
  selectedFileName: string | null = null;

  private readonly destroyRef = inject(DestroyRef);
  private readonly transloco = inject(TranslocoService);

  constructor() {
    this.destroyRef.onDestroy(() => {
      if (this.previewUrl) URL.revokeObjectURL(this.previewUrl);
    });
  }

  onFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    this.validationError.emit('');
    this.clearPreview();

    if (file.size / 1024 / 1024 > this.maxSizeMb()) {
      this.validationError.emit(
        this.transloco.translate('shared.file_upload.file_too_large', { max: this.maxSizeMb() }),
      );
      input.value = '';
      return;
    }

    if (file.type.startsWith('image/')) {
      this.previewUrl = URL.createObjectURL(file);
      this.selectedFileName = null;
    } else {
      this.selectedFileName = file.name;
      this.previewUrl = null;
    }

    this.fileSelected.emit(file);
  }

  clear(fileInput: HTMLInputElement): void {
    this.clearPreview();
    fileInput.value = '';
    this.validationError.emit('');
  }

  private clearPreview(): void {
    if (this.previewUrl) {
      URL.revokeObjectURL(this.previewUrl);
      this.previewUrl = null;
    }
    this.selectedFileName = null;
  }
}
