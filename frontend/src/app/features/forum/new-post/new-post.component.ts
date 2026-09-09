import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

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

/**
 * A failed submit, split by who wrote the sentence (CONTRIBUTING §6).
 *
 *   - `key` is copy of ours. The template pipes it, so a message already on
 *     screen follows a language switch instead of freezing in the language it
 *     was raised in.
 *   - `text` is the API's own `detail` — a finished sentence, shown as-is.
 *     Replacing it with our generic line would cost the reader the one thing
 *     that line cannot tell them: *why* the request failed.
 *
 * Exactly one is ever set; `submitErrorFrom` is the only writer. This is the
 * same shape as `features/auth/auth-error.ts`, deliberately not imported from
 * there — a forum ticket has no business reaching into the auth module. Worth
 * promoting the pair to `core/i18n/` once a third feature needs it.
 */
interface SubmitError {
  key: string;
  text: string;
}

const NO_ERROR: SubmitError = { key: '', text: '' };

/** The API's own explanation when it sent one, our generic key when it did not. */
function submitErrorFrom(err: unknown, fallbackKey: string): SubmitError {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' && detail.trim() !== ''
    ? { key: '', text: detail }
    : { key: fallbackKey, text: '' };
}

@Component({
  selector: 'app-new-post',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
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
    // Start unset rather than snapshotting groupOptions()/sectorOptions() here:
    // currentUser() is still null on first render (populated asynchronously
    // after the /users/me call), so a snapshot would always resolve to the
    // "all" fallback. The effect below fills in the user's own scope once
    // the profile loads.
    group_visibility: this.fb.control<GroupVisibility | null>(null, Validators.required),
    sector_visibility: this.fb.control<SectorVisibility | null>(null, Validators.required),
    // Optional, part of the form group per design, but never sent to the
    // backend: ForumPostCreate has no attachment field, and there's no
    // upload endpoint yet (out of scope – S3 is backlog, see ABF-48 notes).
    // attachment_url will connect here once that endpoint exists.
    attachment: this.fb.control<File | null>(null),
  });

  isLoading = signal(false);
  /** What went wrong on submit, as a key of ours or a sentence the API sent. */
  error = signal<SubmitError>(NO_ERROR);
  /**
   * The size complaint from `app-file-upload`. It arrives already resolved, so
   * unlike `error` it is text and is rendered without the pipe.
   */
  fileError = signal('');

  constructor() {
    // Runs once, the first time currentUser() resolves to a non-null profile.
    // Guarded on the control still being unset so it never clobbers a
    // selection the user already made.
    effect(() => {
      const user = this.auth.currentUser();
      if (!user || this.form.controls.group_visibility.value !== null) return;

      this.form.patchValue({
        group_visibility: this.groupOptions()[0],
        sector_visibility: this.sectorOptions()[0],
      });
    });
  }

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
    this.error.set(NO_ERROR);

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
          this.error.set(submitErrorFrom(err, 'forum.errors.create_failed'));
          this.isLoading.set(false);
        },
      });
  }
}
