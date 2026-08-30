/**
 * Cell members list – entry point for starting a private conversation
 * (ABF-118). Still mounted at /messages: the inbox-of-conversations view
 * this component used to sketch is out of scope for ABF-118 (see the
 * ticket's "לא נכנס" list), so this shows the list of other members in the
 * user's own cell (group+sector) instead — click a name to open the chat.
 */

import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoModule } from '@jsverse/transloco';

import { UserPublic } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

//: Same known-error-key set as chat.component.ts — get_cell_members() only
//: ever denies with _DM_FORBIDDEN_MESSAGE, but any other/unrecognized
//: detail still falls back to a generic message instead of the raw value.
const KNOWN_ERROR_KEYS = ['errors.dm_forbidden', 'errors.internal_server_error'];

function errorKeyFrom(err: unknown): string {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' && KNOWN_ERROR_KEYS.includes(detail)
    ? detail
    : 'errors.generic';
}

@Component({
  selector: 'app-inbox',
  standalone: true,
  imports: [RouterLink, TranslocoModule, LoadingSpinnerComponent, ErrorDisplayComponent],
  templateUrl: './inbox.component.html',
  styleUrl: './inbox.component.scss',
})
export class InboxComponent implements OnInit {
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
