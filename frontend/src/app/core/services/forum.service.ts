/**
 * Forum service.
 *
 * TODO list for junior developer:
 *   [ ] implement reportPost() – POST /forum/posts/:id/report
 *   [ ] implement getInbox() – GET /messages
 *   [ ] implement searchUsers() – GET /users/search?name=...
 */

import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  ConversationSummary,
  DirectMessage,
  DirectMessageCreate,
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

  getInbox(): Observable<ConversationSummary[]> {
    /**
     * TODO:
     *   return this.api.get<ConversationSummary[]>('/messages');
     */
    throw new Error('getInbox() not yet implemented');
  }

  sendMessage(data: DirectMessageCreate): Observable<DirectMessage> {
    return this.api.post<DirectMessage>('/messages', data);
  }

  /**
   * Full history of the conversation with `otherUserId` (no pagination —
   * out of scope for ABF-118). `conversation_key` is a deterministic,
   * non-secret pairing of the two user ids — see buildConversationKey().
   */
  getConversation(myUserId: string, otherUserId: string): Observable<DirectMessage[]> {
    const key = buildConversationKey(myUserId, otherUserId);
    return this.api.get<DirectMessage[]>(`/conversations/${key}/messages`);
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
