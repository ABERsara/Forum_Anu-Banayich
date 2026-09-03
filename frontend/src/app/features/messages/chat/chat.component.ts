/**
 * Chat (direct-message conversation) screen — ABF-118, rebuilt by ABF-120.
 *
 * ABF-118 loaded a conversation whole and appended to the end of it, which is
 * fine for the twenty messages a new conversation has and nothing like the
 * hundreds the ticket describes. This version:
 *
 *   - opens on the newest page and pages backwards on a cursor, so what the
 *     screen asks for does not grow with the conversation;
 *   - loads older messages when the reader nears the top, and holds her place
 *     while they are inserted above her;
 *   - shows a message the instant it is written and takes it back off the
 *     screen if the send fails;
 *   - shows the sender whether the other side has read what she wrote.
 *
 * Still out of scope, and not smuggled in here: searching inside a
 * conversation, deleting a message, and any kind of live update — nothing on
 * this screen polls or subscribes, so a message that arrives while it is open
 * appears on the next load.
 */

import { DatePipe, DecimalPipe } from '@angular/common';
import {
  Component,
  DestroyRef,
  ElementRef,
  Injector,
  OnInit,
  ViewChild,
  afterNextRender,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoModule } from '@jsverse/transloco';

import { DirectMessage, DirectMessageSendResult, UserPublic } from '../../../core/models';
import { AuthService } from '../../../core/services/auth.service';
import { ForumService } from '../../../core/services/forum.service';
import { errorKeyFrom } from '../../../core/utils/error-key.util';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

/** How many messages one history request asks for. */
const PAGE_SIZE = 50;

/** Mirrors DirectMessageCreate.content's max_length on the server. */
const MAX_MESSAGE_LENGTH = 2000;

/**
 * How close to the top of the log counts as "the reader wants what came
 * before". Deliberately a small band rather than exactly 0: a scroll event
 * rarely lands on the pixel, and starting the request slightly early is what
 * makes the older messages arrive before the reader runs out of history.
 */
const OLDER_TRIGGER_PX = 80;

/**
 * One bubble on screen.
 *
 * A view model rather than the API's DirectMessage: `mine` is decided once,
 * here, instead of comparing ids in the template on every change detection,
 * and `pending` has no server counterpart at all — a message that exists only
 * on this screen until the send comes back. Building the two into one shape
 * is what lets the template render an optimistic bubble and a stored one the
 * same way.
 */
export interface ChatMessage {
  /** The server's id, or a local one while the send is still in flight. */
  id: string;
  content: string;
  createdAt: string;
  /** Written by the current user. */
  mine: boolean;
  /** When the other side opened the conversation; null until then. */
  readAt: string | null;
  /** Shown, but not yet acknowledged by the server. */
  pending: boolean;
}

/** What the storage cap cost the conversation on the last send. */
interface PruneNotice {
  count: number;
  limit: number;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [
    RouterLink,
    DatePipe,
    // Groups the thousands in "2,000 characters" and in the cap the prune
    // notice quotes. The numbers are a count, not user content, and a bare
    // "2000" reads as a different order of magnitude at a glance.
    DecimalPipe,
    FormsModule,
    TranslocoModule,
    LoadingSpinnerComponent,
    ErrorDisplayComponent,
  ],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
})
export class ChatComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly forumService = inject(ForumService);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly injector = inject(Injector);

  @ViewChild('messageLog') private messageLog?: ElementRef<HTMLElement>;

  readonly maxLength = MAX_MESSAGE_LENGTH;

  otherUserId = '';
  otherUserName = signal<string>('');

  /** Oldest first — the order the template renders top to bottom. */
  messages = signal<ChatMessage[]>([]);
  draft = signal<string>('');

  isLoading = signal(false);
  loadErrorKey = signal<string>('');
  isLoadingOlder = signal(false);
  olderErrorKey = signal<string>('');
  hasMore = signal(false);
  sendErrorKey = signal<string>('');
  pruneNotice = signal<PruneNotice | null>(null);

  /** How many older messages the last successful page brought in, to announce. */
  olderLoadedCount = signal(0);

  atLimit = computed(() => this.draft().length >= MAX_MESSAGE_LENGTH);
  canSend = computed(() => this.draft().trim().length > 0);

  /** Points at the message *before* the oldest one on screen. */
  private nextCursor: string | null = null;
  private pendingCounter = 0;

  ngOnInit(): void {
    this.otherUserId = this.route.snapshot.paramMap.get('userId') ?? '';
    this.loadCellMemberName();
    this.loadNewestPage();
  }

  /** Which receipt a bubble of the current user's own shows. */
  receiptKey(message: ChatMessage): string {
    if (message.pending) return 'messages.chat.receipt_sending';
    return message.readAt ? 'messages.chat.receipt_read' : 'messages.chat.receipt_sent';
  }

  /**
   * Enter sends; Shift+Enter is left alone so a multi-line message is still
   * possible. Angular's `keydown.enter` binding does not match when a modifier
   * is held, so the Shift case never reaches here.
   */
  onEnter(event: Event): void {
    event.preventDefault();
    this.send();
  }

  onScroll(): void {
    const log = this.messageLog?.nativeElement;
    if (log && log.scrollTop <= OLDER_TRIGGER_PX) this.loadOlder();
  }

  /**
   * Fetch the page before the oldest message on screen.
   *
   * Reachable two ways on purpose. Scrolling is what the ticket asks for, but
   * a scroll event is not something a keyboard user can be relied on to
   * produce, and WCAG 2.1.1 wants every function available from the keyboard —
   * so the same call sits behind a real button at the top of the log.
   */
  loadOlder(): void {
    const myUserId = this.auth.currentUser()?.id;
    const cursor = this.nextCursor;
    if (!myUserId || !cursor || !this.hasMore() || this.isLoadingOlder()) return;

    // Measured *before* the request, not in the callback: by then the new
    // messages are already in the signal and the height has moved.
    const log = this.messageLog?.nativeElement;
    const heightBefore = log?.scrollHeight ?? 0;
    const topBefore = log?.scrollTop ?? 0;

    this.isLoadingOlder.set(true);
    this.olderErrorKey.set('');
    this.forumService
      .getConversation(myUserId, this.otherUserId, { limit: PAGE_SIZE, before: cursor })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (page) => {
          const older = page.items.map((message) => this.toChatMessage(message));
          this.messages.update((current) => [...older, ...current]);
          this.hasMore.set(page.has_more);
          this.nextCursor = page.next_cursor;
          this.isLoadingOlder.set(false);
          this.olderLoadedCount.set(older.length);
          this.anchorScrollAfterPrepend(heightBefore, topBefore);
        },
        error: (err) => {
          this.isLoadingOlder.set(false);
          this.olderErrorKey.set(errorKeyFrom(err, 'messages.chat.load_older_failed'));
        },
      });
  }

  /**
   * Show the message immediately, then reconcile with the server.
   *
   * The bubble is on screen before the request leaves, which is the whole
   * point of an optimistic send — and the reason every failure path below has
   * to put the screen back exactly as it was.
   */
  send(): void {
    const content = this.draft().trim();
    const myUserId = this.auth.currentUser()?.id;
    if (!content || !myUserId) return;

    const localId = `pending-${++this.pendingCounter}`;
    this.messages.update((current) => [
      ...current,
      {
        id: localId,
        content,
        createdAt: new Date().toISOString(),
        mine: true,
        readAt: null,
        pending: true,
      },
    ]);
    this.draft.set('');
    this.sendErrorKey.set('');
    this.pruneNotice.set(null);
    this.scrollToNewest();

    this.forumService
      .sendMessage({ recipient_id: this.otherUserId, content })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => this.onSent(localId, result),
        error: (err) => this.rollback(localId, content, err),
      });
  }

  /** Swap the optimistic bubble for the stored one, and report any pruning. */
  private onSent(localId: string, result: DirectMessageSendResult): void {
    const stored = this.toChatMessage(result.message);
    this.messages.update((current) =>
      current.map((message) => (message.id === localId ? stored : message)),
    );

    if (result.pruned_message_ids.length === 0) return;

    // The server names the messages it deleted rather than just counting
    // them, and this is why: the oldest message on screen is not necessarily
    // one of them — anything under an open report is skipped — so dropping
    // the top of the list by count would remove the wrong bubbles.
    const pruned = new Set(result.pruned_message_ids);
    this.messages.update((current) => current.filter((message) => !pruned.has(message.id)));
    this.pruneNotice.set({
      count: result.pruned_message_ids.length,
      limit: result.conversation_limit,
    });
  }

  /**
   * Take the optimistic bubble back off the screen, and give the text back.
   *
   * The draft is restored only into an empty composer. By the time a send
   * fails the user may already be typing the next message, and replacing what
   * she is writing would cost her more than the failure did. The error line
   * goes up either way, so a rollback is never silent.
   */
  private rollback(localId: string, content: string, err: unknown): void {
    this.messages.update((current) => current.filter((message) => message.id !== localId));
    if (this.draft() === '') this.draft.set(content);
    this.sendErrorKey.set(errorKeyFrom(err, 'messages.chat.send_failed'));
  }

  private loadNewestPage(): void {
    const myUserId = this.auth.currentUser()?.id;
    if (!myUserId) return;

    this.isLoading.set(true);
    this.loadErrorKey.set('');
    this.forumService
      .getConversation(myUserId, this.otherUserId, { limit: PAGE_SIZE })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (page) => {
          this.messages.set(page.items.map((message) => this.toChatMessage(message)));
          this.hasMore.set(page.has_more);
          this.nextCursor = page.next_cursor;
          this.isLoading.set(false);
          this.adoptNameFromHistory(page.items);
          this.scrollToNewest();
        },
        error: (err) => {
          this.loadErrorKey.set(errorKeyFrom(err));
          this.isLoading.set(false);
        },
      });
  }

  private toChatMessage(message: DirectMessage): ChatMessage {
    return {
      id: message.id,
      content: message.content,
      createdAt: message.created_at,
      mine: message.sender.id === this.auth.currentUser()?.id,
      readAt: message.read_at,
      pending: false,
    };
  }

  private loadCellMemberName(): void {
    this.forumService
      .getCellMembers()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (members) => {
          const match = members.find((m: UserPublic) => m.id === this.otherUserId);
          if (match && !this.otherUserName()) this.setOtherUserName(match);
        },
        // A name-lookup failure shouldn't block the conversation itself —
        // and since ABF-120 it does not even cost the name, which the history
        // below carries too.
        error: () => undefined,
      });
  }

  /**
   * Take the other participant's name off the history itself.
   *
   * Every message names both people, so an open conversation knows who it is
   * with without waiting for — or depending on — the cell-members request.
   * That request is still what names an empty conversation, which has no
   * message to read a name from.
   */
  private adoptNameFromHistory(messages: DirectMessage[]): void {
    if (this.otherUserName()) return;
    for (const message of messages) {
      const other = message.sender.id === this.otherUserId ? message.sender : message.recipient;
      if (other.id === this.otherUserId) {
        this.setOtherUserName(other);
        return;
      }
    }
  }

  private setOtherUserName(user: UserPublic): void {
    this.otherUserName.set(`${user.first_name} ${user.last_name}`);
  }

  /**
   * Where the scroll has to land so the same message stays under the same
   * pixel after content is inserted above it.
   *
   * Prepending grows the container upwards, so a scrollTop left alone points
   * at a different message than it did a moment ago — which is the jump the
   * acceptance criterion rules out. Pure arithmetic, and separately tested,
   * because the rule is worth pinning independently of when a browser renders.
   */
  scrollTopAfterPrepend(heightBefore: number, topBefore: number, heightAfter: number): number {
    return heightAfter - heightBefore + topBefore;
  }

  private anchorScrollAfterPrepend(heightBefore: number, topBefore: number): void {
    this.afterRender((log) => {
      log.scrollTop = this.scrollTopAfterPrepend(heightBefore, topBefore, log.scrollHeight);
    });
  }

  private scrollToNewest(): void {
    this.afterRender((log) => {
      log.scrollTop = log.scrollHeight;
    });
  }

  /**
   * Run a DOM measurement once Angular has rendered the pending signal writes.
   *
   * afterNextRender rather than a timeout: scrollHeight only means anything
   * after the new list items exist, and a timeout would let the browser paint
   * the un-anchored list first and correct it a frame later — a visible jump,
   * which is exactly what this is here to prevent.
   */
  private afterRender(adjust: (log: HTMLElement) => void): void {
    afterNextRender(
      () => {
        const log = this.messageLog?.nativeElement;
        if (log) adjust(log);
      },
      { injector: this.injector },
    );
  }
}
