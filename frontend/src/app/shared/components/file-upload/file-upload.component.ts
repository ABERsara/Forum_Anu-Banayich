import { Component, DestroyRef, inject, input, output } from '@angular/core';

@Component({
  selector: 'app-file-upload',
  standalone: true,
  templateUrl: './file-upload.component.html',
  styleUrl: './file-upload.component.scss',
})
export class FileUploadComponent {
  accept = input<string>('image/*,.pdf');
  maxSizeMb = input<number>(5);
  label = input<string>('בחר קובץ');

  fileSelected = output<File>();
  validationError = output<string>();

  previewUrl: string | null = null;
  selectedFileName: string | null = null;

  private readonly destroyRef = inject(DestroyRef);

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
      this.validationError.emit(`הקובץ גדול מדי. הגודל המקסימלי הוא ${this.maxSizeMb()} MB`);
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
