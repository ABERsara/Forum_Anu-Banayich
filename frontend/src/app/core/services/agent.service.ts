/**
 * The AI agents, as the member-facing screens use them (ABF-123).
 *
 * Three calls, and deliberately not the other three the router exposes: the
 * knowledge-base writes under `/agents/{id}/knowledge-entries` are for the
 * professionals who maintain a domain, and reach the screens of a later
 * admin-tools ticket. A service that offered them here would put an editor's
 * verbs one autocomplete away from a member's screen.
 *
 * Nothing is cached. The catalog is filtered server-side by the caller's
 * group/sector, so a cached list would survive a change of account and show a
 * member agents that are not theirs — the same reason `ProfessionalService`
 * re-fetches its catalog on every visit.
 */

import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { AgentChatRequest, AgentChatResponse, AgentConversation, AgentDomain } from '../models';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class AgentService {
  private readonly api = inject(ApiService);

  /**
   * The agents this member may talk to.
   *
   * USER role only — the endpoint answers 403 to an admin or a professional,
   * because this is the member-facing catalog and its filter is built out of
   * the group/sector that only a USER row carries.
   */
  getDomains(): Observable<AgentDomain[]> {
    return this.api.get<AgentDomain[]>('/agents');
  }

  /**
   * Ask one agent a question.
   *
   * `conversationId` is what makes a follow-up a follow-up: with it the server
   * replays the last few turns to the model, so "וכמה זה בערך?" is read next to
   * the question before it. Left out, the server opens a new thread and returns
   * its id — which is why the caller takes the id from the *response* rather
   * than minting one.
   *
   * No timeout here. There is no streaming and Gemini typically takes 3–8
   * seconds, so the screen shows a spinner for as long as this takes; a client
   * that gave up early would leave the member with nothing while the server
   * went on to write both rows anyway.
   */
  chat(domainId: string, message: string, conversationId?: string): Observable<AgentChatResponse> {
    // conversation_id is omitted rather than sent as null: the field is
    // `str | None` with a length bound, and "start a new thread" is the
    // absence of it. Spreading keeps the key off the body entirely.
    const body: AgentChatRequest = {
      message,
      ...(conversationId ? { conversation_id: conversationId } : {}),
    };
    return this.api.post<AgentChatResponse>(`/agents/${domainId}/chat`, body);
  }

  /**
   * One conversation, whole, oldest turn first.
   *
   * What the chat screen calls when it is opened with a thread already in
   * hand. The domain is in the path as well as the conversation: the server
   * checks the agent is still visible to this member before it hands back
   * anything that was said to it.
   */
  getConversation(domainId: string, conversationId: string): Observable<AgentConversation> {
    return this.api.get<AgentConversation>(`/agents/${domainId}/conversations/${conversationId}`);
  }
}
