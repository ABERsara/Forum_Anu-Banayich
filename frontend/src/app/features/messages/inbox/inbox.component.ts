/**
 * Inbox component – list of private conversations.
 *
 * TODO:
 *   1. On init: call ForumService.getInbox()
 *   2. Show each conversation: other person's name, last message preview, unread count
 *   3. Click → navigate to /messages/:userId
 *   4. Add "הודעה חדשה" button → opens user search modal
 *   5. User search: call ForumService.searchUsers(name) – only same group
 *   6. Show unread badge count in header
 *
 * Privacy note: You can only search and message users in YOUR group.
 * No cross-group messaging allowed.
 */

import { Component, OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ConversationSummary } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';

@Component({
  selector: 'app-inbox',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <h1>הודעות פרטיות</h1>
      <!-- TODO: new message button, user search -->
      @for (conv of conversations; track conv.other_user.id) {
        <a
          [routerLink]="['/messages', conv.other_user.id]"
          style="display: block; padding: 0.5rem; border-bottom: 1px solid #ccc"
        >
          <strong>{{ conv.other_user.first_name }} {{ conv.other_user.last_name }}</strong>
          <span> – {{ conv.last_message_preview }}</span>
          @if (conv.unread_count > 0) {
            <span
              style="background: red; color: white; border-radius: 50%; padding: 2px 6px; margin-right: 0.5rem"
            >
              {{ conv.unread_count }}
            </span>
          }
        </a>
      }
      @if (conversations.length === 0 && !isLoading) {
        <p>אין הודעות עדיין.</p>
      }
    </div>
  `,
})
export class InboxComponent implements OnInit {
  private readonly forumService = inject(ForumService);

  conversations: ConversationSummary[] = [];
  isLoading = false;

  ngOnInit(): void {
    this.isLoading = true;
    // TODO: implement
    this.isLoading = false;
  }
}
