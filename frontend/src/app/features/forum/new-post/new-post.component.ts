import { Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import {
  GROUP_VISIBILITY_LABELS,
  GroupVisibility,
  SECTOR_VISIBILITY_LABELS,
  SectorVisibility,
} from '../../../core/constants';
import { AuthService } from '../../../core/services/auth.service';
import { ForumService } from '../../../core/services/forum.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { FileUploadComponent } from '../../../shared/components/file-upload/file-upload.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-new-post',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
    FileUploadComponent,
  ],
  templateUrl: './new-post.component.html',
  styleUrl: './new-post.component.scss',
})
export class NewPostComponent {
  private readonly fb = inject(FormBuilder);
  private readonly forumService = inject(ForumService);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);

  readonly groupVisibilityLabels = GROUP_VISIBILITY_LABELS;
  readonly sectorVisibilityLabels = SECTOR_VISIBILITY_LABELS;

  // A user can only post to their own group/sector or the "everyone" scope.
  // UserType/Sector and GroupVisibility/SectorVisibility share the same string
  // values by design (see core/constants header note) so the cast is safe.
  readonly groupOptions = computed<GroupVisibility[]>(() => {
    const userType = this.auth.currentUser()?.user_type;
    return userType
      ? [userType as unknown as GroupVisibility, GroupVisibility.ALL]
      : [GroupVisibility.ALL];
  });

  readonly sectorOptions = computed<SectorVisibility[]>(() => {
    const sector = this.auth.currentUser()?.sector;
    return sector
      ? [sector as unknown as SectorVisibility, SectorVisibility.ALL]
      : [SectorVisibility.ALL];
  });

  form = this.fb.group({
    title: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(256)]],
    content: ['', [Validators.required, Validators.maxLength(5000)]],
    group_visibility: [GroupVisibility.ALL, Validators.required],
    sector_visibility: [SectorVisibility.ALL, Validators.required],
    // Optional, part of the form group per design, but never sent to the
    // backend: ForumPostCreate has no attachment field, and there's no
    // upload endpoint yet (out of scope – S3 is backlog, see ABF-48 notes).
    // attachment_url will connect here once that endpoint exists.
    attachment: this.fb.control<File | null>(null),
  });

  isLoading = signal(false);
  errorMessage = signal('');
  fileError = signal('');

  get contentLength(): number {
    return this.form.get('content')?.value?.length ?? 0;
  }

  onFileSelected(file: File): void {
    this.fileError.set('');
    this.form.controls.attachment.setValue(file);
  }

  onFileError(message: string): void {
    this.fileError.set(message);
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set('');

    const { title, content, group_visibility, sector_visibility } = this.form.getRawValue();
    this.forumService
      .createPost({
        title: title ?? '',
        content: content ?? '',
        group_visibility: group_visibility ?? GroupVisibility.ALL,
        sector_visibility: sector_visibility ?? SectorVisibility.ALL,
      })
      .subscribe({
        next: (post) => {
          this.isLoading.set(false);
          this.router.navigate(['/forum', post.id]);
        },
        error: (err) => {
          this.errorMessage.set(err.error?.detail ?? 'אירעה שגיאה בפרסום ההודעה.');
          this.isLoading.set(false);
        },
      });
  }
}
