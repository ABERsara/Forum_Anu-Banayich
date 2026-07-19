import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ForumPost } from '../../../core/models';
import { AuthService } from '../../../core/services/auth.service';
import { ForumService } from '../../../core/services/forum.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-edit-post',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, ErrorDisplayComponent, LoadingSpinnerComponent],
  templateUrl: './edit-post.component.html',
  styleUrl: './edit-post.component.scss',
})
export class EditPostComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  private readonly forumService = inject(ForumService);
  private readonly authService = inject(AuthService);

  private postId = '';

  post = signal<ForumPost | null>(null);
  isLoading = signal(false);
  isSaving = signal(false);
  loadError = signal('');
  saveError = signal('');

  // Author-only, unlike delete which also allows moderator/admin — the
  // backend already enforces this; this is just so the form doesn't render
  // for someone who can't save anyway.
  readonly isAuthor = computed(() => {
    const post = this.post();
    const user = this.authService.currentUser();
    return !!post && !!user && post.author.id === user.id;
  });

  form = this.fb.group({
    title: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(256)]],
    content: ['', [Validators.required, Validators.maxLength(5000)]],
  });

  get contentLength(): number {
    return this.form.get('content')?.value?.length ?? 0;
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;
    this.postId = id;
    this.loadPost(id);
  }

  onSubmit(): void {
    if (this.form.invalid || !this.isAuthor()) {
      this.form.markAllAsTouched();
      return;
    }

    this.isSaving.set(true);
    this.saveError.set('');

    const { title, content } = this.form.getRawValue();
    this.forumService
      .updatePost(this.postId, { title: title ?? '', content: content ?? '' })
      .subscribe({
        next: () => {
          this.isSaving.set(false);
          this.router.navigate(['/forum', this.postId]);
        },
        error: (err: HttpErrorResponse) => {
          this.saveError.set(this.messageForError(err));
          this.isSaving.set(false);
        },
      });
  }

  private loadPost(id: string): void {
    this.isLoading.set(true);
    this.loadError.set('');
    this.forumService.getPost(id).subscribe({
      next: (post) => {
        this.post.set(post);
        this.form.patchValue({ title: post.title, content: post.content });
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loadError.set(this.messageForError(err));
        this.isLoading.set(false);
      },
    });
  }

  private messageForError(err: HttpErrorResponse): string {
    if (err.status === 404) return 'ההודעה לא נמצאה.';
    if (err.status === 403) return 'אין לך הרשאה לערוך הודעה זו.';
    return 'אירעה שגיאה. נסה שוב.';
  }
}
