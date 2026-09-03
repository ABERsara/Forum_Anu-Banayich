import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { AdminService } from '../../../core/services/admin.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-broadcast',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
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
  /** What went wrong on send, as a key of ours or a sentence the API sent. */
  error = signal<ScreenError>(NO_ERROR);
  /** Our own confirmation, held as a key so it follows a language switch. */
  successKey = signal('');

  get contentLength(): number {
    return this.form.controls.content.value?.length ?? 0;
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.isLoading.set(true);
    this.error.set(NO_ERROR);
    this.successKey.set('');

    this.adminService
      .sendBroadcast({ title: this.form.value.title!, content: this.form.value.content! })
      .subscribe({
        next: () => {
          this.isLoading.set(false);
          this.successKey.set('admin.broadcast.success');
          this.form.reset();
        },
        error: (err) => {
          this.error.set(screenErrorFrom(err, 'admin.errors.broadcast_failed'));
          this.isLoading.set(false);
        },
      });
  }
}
