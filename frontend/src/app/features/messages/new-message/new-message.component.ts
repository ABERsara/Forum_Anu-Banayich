/**
 * Cell members list – entry point for starting a private conversation
 * (ABF-118). Mounted at /messages/new: the /messages root is the
 * conversations inbox (ABF-119) — this screen is reached from its "new
 * message" link, and shows the list of other members in the user's own
 * cell (group+sector) — click a name to open the chat.
 */

import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoModule } from '@jsverse/transloco';

import { UserPublic } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { errorKeyFrom } from '../../../core/utils/error-key.util';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-new-message',
  standalone: true,
  imports: [RouterLink, TranslocoModule, LoadingSpinnerComponent, ErrorDisplayComponent],
  templateUrl: './new-message.component.html',
  styleUrl: './new-message.component.scss',
})
export class NewMessageComponent implements OnInit {
  private readonly forumService = inject(ForumService);

  members = signal<UserPublic[]>([]);
  isLoading = signal(false);
  hasError = signal(false);
  loadErrorKey = signal('errors.generic');

  ngOnInit(): void {
    this.loadMembers();
  }

  private loadMembers(): void {
    this.isLoading.set(true);
    this.hasError.set(false);
    this.forumService.getCellMembers().subscribe({
      next: (members) => {
        this.members.set(members);
        this.isLoading.set(false);
      },
      error: (err) => {
        this.hasError.set(true);
        this.loadErrorKey.set(errorKeyFrom(err));
        this.isLoading.set(false);
      },
    });
  }
}
