import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AdminService } from '../../../core/services/admin.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-broadcast',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, ErrorDisplayComponent, LoadingSpinnerComponent],
  templateUrl: './broadcast.component.html',
  styleUrl: './broadcast.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BroadcastComponent {
  private readonly fb = inject(FormBuilder);
  private readonly adminService = inject(AdminService);

  form = this.fb.group({
    title: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(256)]],
    content: ['', [Validators.required, Validators.maxLength(5000)]],
  });

  isLoading = signal(false);
  errorMessage = signal('');
  successMessage = signal('');

  get contentLength(): number {
    return this.form.controls.content.value?.length ?? 0;
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set('');
    this.successMessage.set('');

    this.adminService
      .sendBroadcast({ title: this.form.value.title!, content: this.form.value.content! })
      .subscribe({
        next: () => {
          this.isLoading.set(false);
          this.successMessage.set('השידור נשלח בהצלחה לכלל המשתמשים.');
          this.form.reset();
        },
        error: (err) => {
          this.errorMessage.set(err.error?.detail ?? 'שגיאה בשליחת השידור.');
          this.isLoading.set(false);
        },
      });
  }
}
