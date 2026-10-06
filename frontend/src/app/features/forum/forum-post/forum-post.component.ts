/**
 * Single forum post component.
 */

import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { ReportTargetType } from '../../../core/constants';
import { ForumPost } from '../../../core/models';
import { AuthService } from '../../../core/services/auth.service';
import { ForumService } from '../../../core/services/forum.service';
import { MeetingAnnouncementComponent } from '../meeting-announcement/meeting-announcement.component';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';
import { ReportButtonComponent } from '../../../shared/components/report-button/report-button.component';

@Component({
  selector: 'app-forum-post',
  standalone: true,
  imports: [
    RouterLink,
    DatePipe,
    TranslocoPipe,
    LoadingSpinnerComponent,
    ErrorDisplayComponent,
    ConfirmDialogComponent,
    ReportButtonComponent,
    MeetingAnnouncementComponent,
  ],
  templateUrl: './forum-post.component.html',
  styleUrl: './forum-post.component.scss',
})
export class ForumPostComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly forumService = inject(ForumService);
  private readonly authService = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);

  readonly reportTargetType = ReportTargetType.FORUM_POST;

  post = signal<ForumPost | null>(null);
  isLoading = signal(false);
  /**
   * Why these hold a *key* and not the sentence: a failure already on screen
   * has to follow a language switch instead of freezing in the language it was
   * raised in, so the `transloco` pipe runs in the template (CONTRIBUTING §6).
   */
  errorKey = signal<string | null>(null);
  showDeleteConfirm = signal(false);
  deleteErrorKey = signal<string | null>(null);
  likeError = signal(false);
  isLiking = signal(false);

  canDelete = computed(() => {
    const post = this.post();
    const user = this.authService.currentUser();
    if (!post || !user) return false;
    // Deliberate deviation from the ticket's literal AC ("author + admin only") —
    // moderators are shown this button too, per the spec's role definition.
    // Currently role-only (ANY moderator, not just one responsible for this
    // post's author) — pending the reports-triage layer, see ABF-45 notes.
    return (
      post.author.id === user.id || this.authService.isModerator() || this.authService.isAdmin()
    );
  });

  /**
   * A MEETING announcement: published by the system when a
   * professional scheduled a meeting, and read-only. The server refuses both
   * a like and an edit on one, so neither control is drawn — a button that
   * promises an action it cannot perform is worse than no button.
   *
   * Deleting it is not withdrawn. Hiding the announcement is the moderation
   * path the backend was built around: `get_visible_meetings()` stops listing
   * a meeting whose post is no longer VISIBLE. Nor is reporting it.
   *
   * Read from `meeting` rather than from `post_type`: drawing the card needs
   * the object itself, so that one field is the single test for an
   * announcement.
   */
  isMeeting = computed(() => !!this.post()?.meeting);

  // Unlike delete, editing is author-only (ABF-48 AC) — and an announcement
  // is not editable by anyone, its author included.
  canEdit = computed(() => {
    const post = this.post();
    const user = this.authService.currentUser();
    return !!post && !!user && post.author.id === user.id && !this.isMeeting();
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;
    this.loadPost(id);
  }

  onDeleteClick(): void {
    this.deleteErrorKey.set(null);
    this.showDeleteConfirm.set(true);
  }

  onDeleteCancelled(): void {
    this.showDeleteConfirm.set(false);
  }

  toggleLike(): void {
    const post = this.post();
    if (!post || this.isLiking()) return;
    this.likeError.set(false);
    this.isLiking.set(true);
    this.forumService
      .toggleLike(post.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.post.update((current) =>
            current
              ? { ...current, liked_by_me: result.liked, like_count: result.like_count }
              : current,
          );
          this.isLiking.set(false);
        },
        error: () => {
          this.likeError.set(true);
          this.isLiking.set(false);
        },
      });
  }

  onDeleteConfirmed(): void {
    const post = this.post();
    if (!post) return;
    this.showDeleteConfirm.set(false);
    this.forumService.deletePost(post.id).subscribe({
      next: () => this.router.navigate(['/forum']),
      error: () => this.deleteErrorKey.set('forum.errors.delete_failed'),
    });
  }

  private loadPost(id: string): void {
    this.isLoading.set(true);
    this.errorKey.set(null);
    this.forumService.getPost(id).subscribe({
      next: (post) => {
        this.post.set(post);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.errorKey.set(this.errorKeyForStatus(err));
        this.isLoading.set(false);
      },
    });
  }

  private errorKeyForStatus(err: HttpErrorResponse): string {
    if (err.status === 404) return 'forum.errors.not_found';
    if (err.status === 403) return 'forum.errors.view_forbidden';
    return 'forum.errors.load_post_failed';
  }
}
