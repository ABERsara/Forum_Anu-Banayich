/**
 * Single forum post component.
 *
 * TODO:
 *   1. Read :id from route params (ActivatedRoute)
 *   2. Call ForumService.getPost(id) to load the post
 *   3. Display: title, full content, author name, date
 *   4. Show "דיווח" button → opens report modal
 *   5. If current user is the author: show "מחיקה" option (or just hide it)
 *   6. If post has an attachment: show download link
 *   7. Add back navigation → /forum
 */

import { Component, OnInit, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { ForumPost } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';

@Component({
  selector: 'app-forum-post',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <a routerLink="/forum">← חזרה לפורום</a>

      @if (isLoading) {
        <p>טוען...</p>
      } @else if (post) {
        <h1>{{ post.title }}</h1>
        <p>{{ post.author.first_name }} {{ post.author.last_name }} | {{ post.created_at }}</p>
        <p>{{ post.content }}</p>
        <!-- TODO: report button, attachment, delete button for own posts -->
      } @else {
        <p>ההודעה לא נמצאה.</p>
      }
    </div>
  `,
})
export class ForumPostComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly forumService = inject(ForumService);

  post: ForumPost | null = null;
  isLoading = false;

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) return;

    this.isLoading = true;
    // TODO: uncomment when ForumService.getPost() is implemented
    // this.forumService.getPost(id).subscribe({
    //   next: (post) => { this.post = post; this.isLoading = false; },
    //   error: () => { this.isLoading = false; },
    // });
    this.isLoading = false;
  }
}
