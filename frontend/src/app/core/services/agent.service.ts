/**
 * The AI agents, for the two audiences the router serves.
 *
 * Members (ABF-123) use the catalog, the chat and a conversation read. The
 * professionals who maintain a domain (ABF-124) use the knowledge-base calls
 * below. Both sets live in one service because they share one router, and
 * because the server, not the client, decides who may call which: a member
 * who reached an editor's call would get a 403, not a knowledge base.
 *
 * Nothing is cached. The catalog is filtered server-side by the caller's
 * group/sector, so a cached list would survive a change of account and show a
 * member agents that are not theirs — the same reason `ProfessionalService`
 * re-fetches its catalog on every visit. A knowledge base is edited on the
 * very screen that lists it, so a cache there would go stale on the first save.
 */

import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AgentChatRequest,
  AgentChatResponse,
  AgentConversation,
  AgentDomain,
  AgentKnowledgeEntry,
  AgentKnowledgeEntryCreateRequest,
  AgentKnowledgeEntryUpdateRequest,
  PaginatedResponse,
} from '../models';
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

  // -------------------------------------------------------------------------
  // Knowledge base (ABF-124) — ADMIN and PROFESSIONAL only
  // -------------------------------------------------------------------------

  /**
   * The domains whose knowledge base the caller may maintain: every domain for
   * an admin, the domains of their own discipline for a professional.
   *
   * This is how the screen learns which domain ids it may use at all — the
   * member catalog above refuses both roles.
   */
  getManageableDomains(): Observable<AgentDomain[]> {
    return this.api.get<AgentDomain[]>('/agents/manageable');
  }

  /** One page of a domain's knowledge base, most recently edited first. */
  listKnowledgeEntries(
    domainId: string,
    page = 1,
    pageSize = 20,
  ): Observable<PaginatedResponse<AgentKnowledgeEntry>> {
    return this.api.get<PaginatedResponse<AgentKnowledgeEntry>>(
      `/agents/${domainId}/knowledge-entries?page=${page}&page_size=${pageSize}`,
    );
  }

  /** Add an entry. The server indexes it for retrieval before it answers. */
  createKnowledgeEntry(
    domainId: string,
    body: AgentKnowledgeEntryCreateRequest,
  ): Observable<AgentKnowledgeEntry> {
    return this.api.post<AgentKnowledgeEntry>(`/agents/${domainId}/knowledge-entries`, body);
  }

  /**
   * Edit an entry — only the fields in `body` are written.
   *
   * The server re-indexes when `title` or `content` is present, so a caller
   * should send just what changed rather than the whole form.
   */
  updateKnowledgeEntry(
    domainId: string,
    entryId: string,
    body: AgentKnowledgeEntryUpdateRequest,
  ): Observable<AgentKnowledgeEntry> {
    return this.api.patch<AgentKnowledgeEntry>(
      `/agents/${domainId}/knowledge-entries/${entryId}`,
      body,
    );
  }

  /** Remove an entry; the agent stops drawing on it at once. */
  deleteKnowledgeEntry(domainId: string, entryId: string): Observable<void> {
    return this.api.delete<void>(`/agents/${domainId}/knowledge-entries/${entryId}`);
  }
}
