/**
 * New post form component.
 *
 * TODO:
 *   1. Build a reactive form:
 *      - title (required, min 2, max 256)
 *      - content (required, min 1, max 5000)
 *      - group_visibility (required) – use GroupVisibility enum
 *      - sector_visibility (required) – use SectorVisibility enum
 *      - attachment (optional, max 5MB, PDF or image)
 *   2. On submit: call ForumService.createPost()
 *   3. On success: navigate to the new post /forum/:id
 *   4. Character counter for content (show remaining of 5000)
 *   5. Explain what each visibility option means in the UI:
 *      e.g. "תא שלי" = only my group + sector
 *
 * Note on visibility:
 *   The logged-in user can only post to their own group or broader.
 *   They CANNOT post to a DIFFERENT group (e.g. a widow cannot post to widowers).
 *   The backend enforces this, but the UI should prevent it too.
 */

import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { GroupVisibility, SectorVisibility } from '../../../core/constants';
import { ForumService } from '../../../core/services/forum.service';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-new-post',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <a routerLink="/forum">← חזרה לפורום</a>
      <h1>פרסום הודעה חדשה</h1>

      <form (ngSubmit)="onSubmit()">
        <!-- TODO: build real form here -->
        <p>TODO: implement new post form</p>
        <p>כותרת, תוכן, טווח הפצה, קובץ מצורף</p>
        <button type="submit">פרסם</button>
      </form>
    </div>
  `,
})
export class NewPostComponent {
  private readonly fb = inject(FormBuilder);
  private readonly forumService = inject(ForumService);
  private readonly router = inject(Router);
  readonly auth = inject(AuthService);

  form = this.fb.group({
    title: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(256)]],
    content: ['', [Validators.required, Validators.maxLength(5000)]],
    group_visibility: [GroupVisibility.ALL, Validators.required],
    sector_visibility: [SectorVisibility.ALL, Validators.required],
  });

  isLoading = false;

  get contentLength(): number {
    return this.form.get('content')?.value?.length ?? 0;
  }

  onSubmit(): void {
    if (this.form.invalid) return;
    // TODO: implement
  }
}
