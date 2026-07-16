/**
 * Single forum post component.
 */

import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ReportTargetType } from '../../../core/constants';
import { ForumPost } from '../../../core/models';
import { AuthService } from '../../../core/services/auth.service';
import { ForumService } from '../../../core/services/forum.service';
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
    LoadingSpinnerComponent,
    ErrorDisplayComponent,
    ConfirmDialogComponent,
    ReportButtonComponent,
  ],
  templateUrl: './forum-post.component.html',
  styleUrl: './forum-post.component.scss',
})
export class ForumPostComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly forumService = inject(ForumService);
  private readonly authService = inject(AuthService);

  readonly reportTargetType = ReportTargetType.FORUM_POST;

  post = signal<ForumPost | null>(null);
  isLoading = signal(false);
  errorMessage = signal<string | null>(null);
  showDeleteConfirm = signal(false);
  deleteError = signal<string | null>(null);

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

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;
    this.loadPost(id);
  }

  onDeleteClick(): void {
    this.deleteError.set(null);
    this.showDeleteConfirm.set(true);
  }

  onDeleteCancelled(): void {
    this.showDeleteConfirm.set(false);
  }

  onDeleteConfirmed(): void {
    const post = this.post();
    if (!post) return;
    this.showDeleteConfirm.set(false);
    this.forumService.deletePost(post.id).subscribe({
      next: () => this.router.navigate(['/forum']),
      error: () => this.deleteError.set('אירעה שגיאה במחיקת ההודעה. נסה שוב.'),
    });
  }

  private loadPost(id: string): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.forumService.getPost(id).subscribe({
      next: (post) => {
        this.post.set(post);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.errorMessage.set(this.messageForError(err));
        this.isLoading.set(false);
      },
    });
  }

  private messageForError(err: HttpErrorResponse): string {
    if (err.status === 404) return 'ההודעה לא נמצאה.';
    if (err.status === 403) return 'אין לך הרשאה לצפות בהודעה זו.';
    return 'אירעה שגיאה בטעינת ההודעה. נסה לרענן את הדף.';
  }
}
