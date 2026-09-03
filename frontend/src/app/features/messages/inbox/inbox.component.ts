/**
 * Conversations inbox (ABF-119) – mounted at /messages.
 *
 * Lists the user's existing conversations (other participant, last message
 * preview, date, unread count), most recent first. Starting a *new*
 * conversation is a separate screen (NewMessageComponent, /messages/new) –
 * this one only shows conversations that already have at least one message.
 */

import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { TranslocoModule } from '@jsverse/transloco';
import { Subscription } from 'rxjs';

import { ConversationSummary } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { errorKeyFrom } from '../../../core/utils/error-key.util';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-inbox',
  standalone: true,
  imports: [RouterLink, DatePipe, TranslocoModule, LoadingSpinnerComponent, ErrorDisplayComponent],
  templateUrl: './inbox.component.html',
  styleUrl: './inbox.component.scss',
})
export class InboxComponent implements OnInit {
  private readonly forumService = inject(ForumService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly pageSize = 20;
  private loadSubscription?: Subscription;

  conversations = signal<ConversationSummary[]>([]);
  isLoading = signal(false);
  hasError = signal(false);
  loadErrorKey = signal('errors.generic');
  page = signal(1);
  total = signal(0);

  totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.pageSize)));

  ngOnInit(): void {
    this.loadInbox(this.page());
  }

  otherUserName(conversation: ConversationSummary): string {
    return `${conversation.other_user.first_name} ${conversation.other_user.last_name}`;
  }

  nextPage(): void {
    if (this.page() < this.totalPages()) {
      this.loadInbox(this.page() + 1);
    }
  }

  previousPage(): void {
    if (this.page() > 1) {
      this.loadInbox(this.page() - 1);
    }
  }

  private loadInbox(page: number): void {
    // A previous page request still in flight must not let a late, now-stale
    // response overwrite a newer one (e.g. rapid next/previous clicks) —
    // cancel it, same pattern as qa-feed.component.ts's load().
    this.loadSubscription?.unsubscribe();

    this.isLoading.set(true);
    this.hasError.set(false);
    this.loadSubscription = this.forumService
      .getInbox(page, this.pageSize)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.conversations.set(result.items);
          this.total.set(result.total);
          this.page.set(result.page);
          this.isLoading.set(false);
        },
        error: (err) => {
          this.hasError.set(true);
          this.loadErrorKey.set(errorKeyFrom(err));
          this.isLoading.set(false);
        },
      });
  }
}
