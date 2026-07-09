/**
 * Forum list component – shows all posts visible to the current user.
 *
 * TODO:
 *   1. On init: call ForumService.getPosts() and display the results
 *   2. Implement infinite scroll OR pagination (next/prev buttons)
 *   3. Show each post as a card: title, author name (only), date, excerpt
 *   4. Add "פרסום הודעה חדשה" button → navigate to /forum/new
 *   5. Add "דיווח" button on each post card (opens a modal)
 *   6. Show loading spinner while fetching
 *   7. Show empty state if no posts
 *   8. Add group/sector visibility badge on each post
 *      (e.g. "לאלמנות חסידיות" vs "לכל הקבוצה")
 *
 * Notes:
 *   - The backend filters posts automatically – don't add client-side filtering
 *   - Use RTL layout (Hebrew)
 */

import { Component, OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ForumPost } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { DatePipe } from '@angular/common';

@Component({
  selector: 'app-forum-list',
  standalone: true,
  imports: [RouterLink, DatePipe],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <div style="display: flex; justify-content: space-between; align-items: center">
        <h1>פורום הקהילה</h1>
        <a routerLink="/forum/new">+ פרסום הודעה חדשה</a>
      </div>

      @if (isLoading) {
        <p>טוען...</p>
      } @else if (posts.length === 0) {
        <p>אין הודעות עדיין. היי הראשונ/ה לפרסם!</p>
      } @else {
        @for (post of posts; track post.id) {
          <div style="border: 1px solid #ccc; margin: 0.5rem 0; padding: 1rem; border-radius: 8px">
            <a [routerLink]="['/forum', post.id]">
              <strong>{{ post.title }}</strong>
            </a>
            <p>
              {{ post.author.first_name }} {{ post.author.last_name }} |
              {{ post.created_at | date }}
            </p>
            <!-- TODO: show excerpt, visibility badge, report button -->
          </div>
        }
      }
    </div>
  `,
})
export class ForumListComponent implements OnInit {
  private readonly forumService = inject(ForumService);

  posts: ForumPost[] = [];
  isLoading = false;

  ngOnInit(): void {
    this.loadPosts();
  }

  private loadPosts(): void {
    this.isLoading = true;
    // TODO: uncomment when ForumService.getPosts() is implemented
    // this.forumService.getPosts().subscribe({
    //   next: (result) => {
    //     this.posts = result.items;
    //     this.isLoading = false;
    //   },
    //   error: () => { this.isLoading = false; },
    // });
    this.isLoading = false;
  }
}
