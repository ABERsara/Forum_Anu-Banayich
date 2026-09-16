/**
 * The conversation with one AI agent (ABF-123).
 *
 * There is no streaming: `POST /agents/{id}/chat` answers once, and Gemini
 * typically takes 3–8 seconds to get there. Everything below follows from that
 * one fact — the member's own question goes up the moment it is sent, a
 * spinner sits where the answer will be, and the composer is closed until the
 * answer arrives, so the screen is never a frozen page with a cursor blinking
 * in it.
 *
 * **Where the agent's name comes from.** There is no `GET /agents/{id}`: the
 * catalog is the only place a domain's name and discipline are published, so
 * this screen loads it and looks its own id up in it. That is not a detour —
 * the catalog is already filtered to what this member may see, so an id that
 * is not in it is exactly the case that has to be refused, and the lookup is
 * both the name resolution and the permission check.
 *
 * **The disclaimer appears twice, and that is not a bug.** The banner is the
 * standing notice SPEC §12 requires in the interface; the paragraph at the
 * foot of each answer is part of the stored `agent_messages` row, concatenated
 * by `agent_service._compose_answer()` so that it cannot be dropped or
 * paraphrased, and read back months later by whoever opens the thread. Neither
 * stands in for the other: the banner is on screen before the first answer and
 * after the last, and the stored line is what an exported conversation carries
 * when there is no banner around it. The backend documents this screen as
 * replaying the stored content verbatim, so nothing here strips it.
 *
 * **Out of scope, and not smuggled in:** a list of past conversations. A
 * thread reached through `?conversation=` is loaded, and the id of a thread
 * started here is written back into the URL so a refresh does not lose it —
 * but the screen that lists a member's threads is a later ticket.
 */

import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { AgentMessageRole } from '../../../core/constants';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { AgentDomain, AgentMessage, AgentSource } from '../../../core/models';
import { AgentService } from '../../../core/services/agent.service';
import { DisclaimerBannerComponent } from '../../../shared/components/disclaimer-banner/disclaimer-banner.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

/**
 * Mirrors `settings.AGENT_MAX_MESSAGE_LENGTH`, which the request schema reads
 * at import time. Enforced here so an over-long question is caught before it
 * costs a round trip — the server is still the one that decides, and a change
 * there that is not mirrored here turns into a 422 the screen shows rather
 * than a silent truncation.
 */
const MAX_MESSAGE_LENGTH = 1000;

/** The query parameter a thread is re-opened through. */
const CONVERSATION_PARAM = 'conversation';

/**
 * One turn as the screen holds it.
 *
 * Wider than `AgentMessage` in two places, both of which the API cannot carry:
 * `sources` belongs to the exchange rather than to the row, so it exists only
 * for answers received in this session and never for a thread loaded back; and
 * `pending` marks a question that is on screen but not yet written anywhere.
 */
interface ChatTurn {
  id: string;
  role: AgentMessageRole;
  content: string;
  createdAt: string;
  sources: AgentSource[];
  pending: boolean;
}

const asTurn = (message: AgentMessage, sources: AgentSource[] = []): ChatTurn => ({
  id: message.id,
  role: message.role,
  content: message.content,
  createdAt: message.created_at,
  sources,
  pending: false,
});

@Component({
  selector: 'app-agent-chat',
  imports: [
    DatePipe,
    DecimalPipe,
    FormsModule,
    RouterLink,
    TranslocoPipe,
    DisclaimerBannerComponent,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
  templateUrl: './agent-chat.component.html',
  styleUrl: './agent-chat.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgentChatComponent implements OnInit {
  /** Bound from the :domainId route parameter (withComponentInputBinding). */
  readonly domainId = input.required<string>();

  private readonly agentService = inject(AgentService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly domain = signal<AgentDomain | null>(null);
  readonly turns = signal<ChatTurn[]>([]);
  readonly draft = signal('');

  /** The catalog lookup and, when the route names one, the thread behind it. */
  readonly isLoading = signal(false);
  /** One question in flight. What the spinner in the log is waiting on. */
  readonly isSending = signal(false);

  /** The screen could not be opened at all — no composer is shown under it. */
  readonly loadError = signal<ScreenError>(NO_ERROR);
  /** The last question failed. The screen still works; this one did not. */
  readonly sendError = signal<ScreenError>(NO_ERROR);

  readonly maxLength = MAX_MESSAGE_LENGTH;
  readonly roles = AgentMessageRole;

  /**
   * The open thread, once there is one.
   *
   * Taken from the first response rather than minted here: the id is the
   * server's, and sending one it never issued would be a 404 on every
   * follow-up.
   */
  private readonly conversationId = signal<string | undefined>(undefined);

  readonly isReady = computed(() => this.domain() !== null);
  readonly atLimit = computed(() => this.draft().length >= MAX_MESSAGE_LENGTH);
  readonly canSend = computed(
    () => this.isReady() && !this.isSending() && this.draft().trim().length > 0,
  );

  /**
   * Where "ask a human instead" goes: the advice form, with the discipline
   * this agent covers already chosen. `professional_domain` is why ABF-123
   * needed it on the catalog — an agent id is a uuid, and nothing else on this
   * screen says which profession the member has been talking about.
   */
  readonly referralParams = computed(() => ({ domain: this.domain()?.professional_domain }));

  ngOnInit(): void {
    this.isLoading.set(true);

    this.agentService.getDomains().subscribe({
      next: (domains) => {
        const domain = domains.find((candidate) => candidate.id === this.domainId());
        if (!domain) {
          // Not "not found": the catalog is already filtered, so an id missing
          // from it is either an agent that does not exist or one this member
          // may not use, and the screen must not tell them which.
          this.loadError.set({ key: 'agents.errors.domain_unavailable', text: '' });
          this.isLoading.set(false);
          return;
        }

        this.domain.set(domain);
        this.loadOpenThread();
      },
      error: (err) => {
        this.loadError.set(screenErrorFrom(err, 'agents.errors.load_domains_failed'));
        this.isLoading.set(false);
      },
    });
  }

  /**
   * The thread named in `?conversation=`, when the member arrived with one.
   *
   * Read off the snapshot rather than bound as an input: `rememberThread()`
   * writes this same parameter back, and an input bound to it would re-enter
   * here on every answer and reload the conversation already on screen.
   */
  private loadOpenThread(): void {
    const openThread = this.route.snapshot.queryParamMap.get(CONVERSATION_PARAM);
    if (!openThread) {
      this.isLoading.set(false);
      return;
    }

    this.agentService.getConversation(this.domainId(), openThread).subscribe({
      next: (conversation) => {
        this.conversationId.set(conversation.id);
        this.turns.set(conversation.messages.map((message) => asTurn(message)));
        this.isLoading.set(false);
      },
      error: (err) => {
        // A failed history load is not a dead screen: the agent is still there
        // and a new thread can be started, which is what the message says.
        this.sendError.set(screenErrorFrom(err, 'agents.errors.load_conversation_failed'));
        this.isLoading.set(false);
      },
    });
  }

  /** Enter sends; Shift+Enter is a newline, as in the direct-message composer. */
  onEnter(event: Event): void {
    if ((event as KeyboardEvent).shiftKey) return;

    event.preventDefault();
    this.send();
  }

  send(): void {
    if (!this.canSend()) return;

    const question = this.draft().trim();
    const pending: ChatTurn = {
      // Local, and never sent anywhere: the server's id arrives with the echo
      // of the question and replaces this turn whole.
      id: `pending-${Date.now()}`,
      role: AgentMessageRole.USER,
      content: question,
      createdAt: new Date().toISOString(),
      sources: [],
      pending: true,
    };

    this.draft.set('');
    this.sendError.set(NO_ERROR);
    this.turns.update((turns) => [...turns, pending]);
    this.isSending.set(true);

    this.agentService.chat(this.domainId(), question, this.conversationId()).subscribe({
      next: (response) => {
        this.conversationId.set(response.conversation_id);
        this.turns.update((turns) => [
          ...turns.filter((turn) => turn.id !== pending.id),
          // The question as the server stored it, not as it was typed: its id
          // and timestamp are the server's, and the thread is rendered from
          // them.
          asTurn(response.question),
          asTurn(response.answer, response.sources),
        ]);
        this.isSending.set(false);
        this.rememberThread(response.conversation_id);
      },
      error: (err) => {
        // The question comes back off the screen and back into the box. A 429
        // after eight hundred characters must not cost the member what they
        // wrote.
        this.turns.update((turns) => turns.filter((turn) => turn.id !== pending.id));
        this.draft.set(question);
        this.sendError.set(screenErrorFrom(err, 'agents.errors.send_failed'));
        this.isSending.set(false);
      },
    });
  }

  /**
   * Puts the thread id in the address bar, so a refresh returns to the
   * conversation instead of opening an empty one.
   *
   * `replaceUrl` — the thread is the same screen, not a place to go back to; a
   * history entry per answer would make the browser's back button walk the
   * conversation instead of leaving it.
   */
  private rememberThread(conversationId: string): void {
    if (this.route.snapshot.queryParamMap.get(CONVERSATION_PARAM) === conversationId) return;

    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { [CONVERSATION_PARAM]: conversationId },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
