/**
 * Forum list component – shows all posts visible to the current user.
 *
 * The backend filters posts automatically – don't add client-side filtering.
 */

import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
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
  private readonly pageSize = 20;

  posts = signal<ForumPost[]>([]);
  isLoading = signal(false);
  hasError = signal(false);
  page = signal(1);
  total = signal(0);

  totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.pageSize)));

  readonly groupVisibilityLabels = GROUP_VISIBILITY_LABELS;
  readonly sectorVisibilityLabels = SECTOR_VISIBILITY_LABELS;

  ngOnInit(): void {
    this.loadPosts(this.page());
  }

  nextPage(): void {
    if (this.page() < this.totalPages()) {
      this.loadPosts(this.page() + 1);
    }
  }

  previousPage(): void {
    if (this.page() > 1) {
      this.loadPosts(this.page() - 1);
    }
  }

  private loadPosts(page: number): void {
    this.isLoading.set(true);
    this.hasError.set(false);
    this.forumService.getPosts(page, this.pageSize).subscribe({
      next: (result) => {
        this.posts.set(result.items);
        this.total.set(result.total);
        this.page.set(result.page);
        this.isLoading.set(false);
      },
      error: () => {
        this.hasError.set(true);
        this.isLoading.set(false);
      },
    });
  }
}
