/**
 * Forum service.
 *
 * TODO list for junior developer:
 *   [ ] implement reportPost() – POST /forum/posts/:id/report
 *   [ ] implement searchUsers() – GET /users/search?name=...
 */

import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  ConversationList,
  ConversationMessagesPage,
  DirectMessageCreate,
  DirectMessageSendResult,
  ForumPost,
  ForumPostCreate,
  ForumPostList,
  ForumPostUpdate,
  ReportCreate,
  UserPublic,
} from '../models';
import { ApiService } from './api.service';

/**
 * Deterministic conversation key for a pair of user ids — must produce the
 * exact same string as the backend's forum_service.build_conversation_key()
 * (Python's sorted() and this both sort ASCII UUID strings lexicographically,
 * so they agree). Not a secret: both participants already know each other's
 * id from the cell-members list.
 */
export function buildConversationKey(userIdA: string, userIdB: string): string {
  return [userIdA, userIdB].sort().join(':');
}

@Injectable({ providedIn: 'root' })
export class ForumService {
  private readonly api = inject(ApiService);

  getPosts(page = 1, pageSize = 20): Observable<ForumPostList> {
    // The backend automatically filters by the user's group+sector.
    // Do NOT add any client-side filtering.
    return this.api.get<ForumPostList>(`/forum/posts?page=${page}&page_size=${pageSize}`);
  }

  getPost(id: string): Observable<ForumPost> {
    return this.api.get<ForumPost>(`/forum/posts/${id}`);
  }

  deletePost(id: string): Observable<ForumPost> {
    return this.api.delete<ForumPost>(`/forum/posts/${id}`);
  }

  createPost(data: ForumPostCreate): Observable<ForumPost> {
    return this.api.post<ForumPost>('/forum/posts', data);
  }

  updatePost(id: string, data: ForumPostUpdate): Observable<ForumPost> {
    return this.api.patch<ForumPost>(`/forum/posts/${id}`, data);
  }

  reportPost(postId: string, data: ReportCreate): Observable<unknown> {
    void postId;
    void data;
    /**
     * TODO:
     *   return this.api.post(`/forum/posts/${postId}/report`, data);
     */
    throw new Error('reportPost() not yet implemented');
  }

  // ──────────────────────────────────────────────────────────
  // Direct messages
  // ──────────────────────────────────────────────────────────

  getInbox(page = 1, pageSize = 20): Observable<ConversationList> {
    return this.api.get<ConversationList>(`/messages?page=${page}&page_size=${pageSize}`);
  }

  sendMessage(data: DirectMessageCreate): Observable<DirectMessageSendResult> {
    return this.api.post<DirectMessageSendResult>('/messages', data);
  }

  /**
   * One page of the conversation with `otherUserId`, oldest first within the
   * page. `conversation_key` is a deterministic, non-secret pairing of the two
   * user ids — see buildConversationKey().
   *
   * Call it with no `before` for the newest page, which is what the screen
   * opens on, then pass each response's `next_cursor` back as `before` to walk
   * backwards. That first, cursor-less request is also the one that marks the
   * conversation read on the server, so scrolling back through history stays a
   * pure read.
   */
  getConversation(
    myUserId: string,
    otherUserId: string,
    options: { limit?: number; before?: string | null } = {},
  ): Observable<ConversationMessagesPage> {
    const key = buildConversationKey(myUserId, otherUserId);
    const params = new URLSearchParams();
    if (options.limit !== undefined) params.set('limit', String(options.limit));
    if (options.before) params.set('before', options.before);
    const query = params.toString();
    return this.api.get<ConversationMessagesPage>(
      `/conversations/${key}/messages${query ? `?${query}` : ''}`,
    );
  }

  /** Other ACTIVE members of the current user's own cell (group+sector). */
  getCellMembers(): Observable<UserPublic[]> {
    return this.api.get<UserPublic[]>('/cells/me/members');
  }

  searchUsers(name: string): Observable<UserPublic[]> {
    void name;
    /**
     * TODO:
     *   return this.api.get<UserPublic[]>(`/users/search?name=${encodeURIComponent(name)}`);
     *
     * Only users in the same group are returned (backend enforced).
     */
    throw new Error('searchUsers() not yet implemented');
  }
}
