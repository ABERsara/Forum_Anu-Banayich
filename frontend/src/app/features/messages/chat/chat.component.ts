/**
 * Chat (direct message conversation) component (ABF-118).
 *
 * No pagination, no read-receipts, no auto-refresh/WebSocket — all
 * explicitly out of scope for this ticket (see its "לא נכנס" list). This is
 * the "מסך שיחה מינימלי" the ticket asks for: load the full history once,
 * send new messages, done.
 */

import { Component, ElementRef, OnInit, ViewChild, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';

import { DirectMessage, UserPublic } from '../../../core/models';
import { AuthService } from '../../../core/services/auth.service';
import { ForumService } from '../../../core/services/forum.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [RouterLink, FormsModule, LoadingSpinnerComponent, ErrorDisplayComponent],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
})
export class ChatComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly forumService = inject(ForumService);
  private readonly auth = inject(AuthService);

  @ViewChild('messagesEnd') private messagesEnd?: ElementRef<HTMLElement>;

  otherUserId = '';
  otherUserName = signal<string>('');
  messages = signal<DirectMessage[]>([]);
  newMessage = '';

  isLoading = signal(false);
  hasError = signal(false);
  isSending = signal(false);
  sendError = signal(false);

  ngOnInit(): void {
    this.otherUserId = this.route.snapshot.paramMap.get('userId') ?? '';
    this.loadCellMemberName();
    this.loadConversation();
  }

  isMyMessage(msg: DirectMessage): boolean {
    return msg.sender.id === this.auth.currentUser()?.id;
  }

  sendMessage(): void {
    const content = this.newMessage.trim();
    if (!content || this.isSending()) return;

    this.isSending.set(true);
    this.sendError.set(false);
    this.forumService.sendMessage({ recipient_id: this.otherUserId, content }).subscribe({
      next: (message) => {
        this.messages.update((current) => [...current, message]);
        this.newMessage = '';
        this.isSending.set(false);
        this.scrollToBottom();
      },
      error: () => {
        this.isSending.set(false);
        this.sendError.set(true);
      },
    });
  }

  private loadConversation(): void {
    const myUserId = this.auth.currentUser()?.id;
    if (!myUserId) return;

    this.isLoading.set(true);
    this.hasError.set(false);
    this.forumService.getConversation(myUserId, this.otherUserId).subscribe({
      next: (messages) => {
        this.messages.set(messages);
        this.isLoading.set(false);
        this.scrollToBottom();
      },
      error: () => {
        this.hasError.set(true);
        this.isLoading.set(false);
      },
    });
  }

  private loadCellMemberName(): void {
    this.forumService.getCellMembers().subscribe({
      next: (members) => {
        const match = members.find((m: UserPublic) => m.id === this.otherUserId);
        if (match) this.otherUserName.set(`${match.first_name} ${match.last_name}`);
      },
      // A name-lookup failure shouldn't block the conversation itself.
      error: () => undefined,
    });
  }

  private scrollToBottom(): void {
    // scrollIntoView isn't implemented in every test DOM environment —
    // guard its existence rather than assume a real browser.
    queueMicrotask(() => this.messagesEnd?.nativeElement.scrollIntoView?.());
  }
}
