/**
 * Forum list component – shows all posts visible to the current user.
 *
 * The backend filters posts automatically – don't add client-side filtering.
 */

import { DatePipe } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { GROUP_VISIBILITY_LABELS, SECTOR_VISIBILITY_LABELS } from '../../../core/constants';
import { ForumPost } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-forum-list',
  standalone: true,
  imports: [RouterLink, DatePipe, LoadingSpinnerComponent, ErrorDisplayComponent],
  templateUrl: './forum-list.component.html',
  styleUrl: './forum-list.component.scss',
})
export class ForumListComponent implements OnInit {
  private readonly forumService = inject(ForumService);

  posts: ForumPost[] = [];
  isLoading = false;
  hasError = false;
  page = 1;
  pageSize = 20;
  total = 0;

  readonly groupVisibilityLabels = GROUP_VISIBILITY_LABELS;
  readonly sectorVisibilityLabels = SECTOR_VISIBILITY_LABELS;

  get totalPages(): number {
    return Math.max(1, Math.ceil(this.total / this.pageSize));
  }

  ngOnInit(): void {
    this.loadPosts(this.page);
  }

  nextPage(): void {
    if (this.page < this.totalPages) {
      this.loadPosts(this.page + 1);
    }
  }

  previousPage(): void {
    if (this.page > 1) {
      this.loadPosts(this.page - 1);
    }
  }

  private loadPosts(page: number): void {
    this.isLoading = true;
    this.hasError = false;
    this.forumService.getPosts(page, this.pageSize).subscribe({
      next: (result) => {
        this.posts = result.items;
        this.total = result.total;
        this.page = result.page;
        this.isLoading = false;
      },
      error: () => {
        this.hasError = true;
        this.isLoading = false;
      },
    });
  }
}
