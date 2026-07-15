/**
 * Forum service.
 *
 * TODO list for junior developer:
 *   [ ] implement getPosts() – GET /forum/posts
 *   [ ] implement getPost() – GET /forum/posts/:id
 *   [ ] implement createPost() – POST /forum/posts
 *   [ ] implement reportPost() – POST /forum/posts/:id/report
 *   [ ] implement getInbox() – GET /messages
 *   [ ] implement sendMessage() – POST /messages
 *   [ ] implement getConversation() – GET /messages/:userId
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
  ReportCreate,
  UserPublic,
} from '../models';
import { ApiService } from './api.service';

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
    void data;
    /**
     * TODO:
     *   return this.api.post<ForumPost>('/forum/posts', data);
     */
    throw new Error('createPost() not yet implemented');
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
    void data;
    /**
     * TODO:
     *   return this.api.post<DirectMessage>('/messages', data);
     */
    throw new Error('sendMessage() not yet implemented');
  }

  getConversation(userId: string, page = 1): Observable<DirectMessage[]> {
    void userId;
    void page;
    /**
     * TODO:
     *   return this.api.get<DirectMessage[]>(`/messages/${userId}?page=${page}`);
     */
    throw new Error('getConversation() not yet implemented');
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
