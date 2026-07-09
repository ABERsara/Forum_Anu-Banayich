/**
 * Chat (direct message conversation) component.
 *
 * TODO:
 *   1. Read :userId from route params
 *   2. Load conversation with ForumService.getConversation(userId)
 *   3. Display messages in chat bubble style (own messages on left since RTL)
 *   4. Text input at the bottom to send new messages
 *   5. On send: call ForumService.sendMessage({ recipient_id, content })
 *   6. Auto-scroll to bottom on new messages
 *   7. Show "דיווח" button on each received message
 *   8. Auto-refresh messages every 30 seconds (or use WebSocket in v2)
 */

import { Component, OnInit, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';

import { DirectMessage } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [RouterLink, FormsModule],
  template: `
    <div
      style="padding: 1rem; direction: rtl; display: flex; flex-direction: column; height: 100vh"
    >
      <a routerLink="/messages">← חזרה לתיבת הדואר</a>

      <!-- Messages -->
      <div style="flex: 1; overflow-y: auto; padding: 1rem">
        @for (msg of messages; track msg.id) {
          <div [style.text-align]="isMyMessage(msg) ? 'left' : 'right'" style="margin: 0.5rem 0">
            <span
              style="background: #e5e7eb; padding: 0.5rem 1rem; border-radius: 12px; display: inline-block"
            >
              {{ msg.content }}
            </span>
          </div>
        }
      </div>

      <!-- Input -->
      <div style="padding: 1rem; border-top: 1px solid #ccc; display: flex; gap: 0.5rem">
        <input
          [(ngModel)]="newMessage"
          placeholder="כתבי הודעה..."
          style="flex: 1; padding: 0.5rem"
          (keyup.enter)="sendMessage()"
        />
        <button (click)="sendMessage()">שלח</button>
      </div>
    </div>
  `,
})
export class ChatComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly forumService = inject(ForumService);
  readonly auth = inject(AuthService);

  otherUserId = '';
  messages: DirectMessage[] = [];
  newMessage = '';

  ngOnInit(): void {
    this.otherUserId = this.route.snapshot.paramMap.get('userId') ?? '';
    // TODO: load conversation
  }

  isMyMessage(msg: DirectMessage): boolean {
    return msg.sender.id === this.auth.currentUser()?.id;
  }

  sendMessage(): void {
    if (!this.newMessage.trim()) return;
    // TODO: implement
    this.newMessage = '';
  }
}
