/**
 * Cell members list – entry point for starting a private conversation
 * (ABF-118). Mounted at /messages/new: the /messages root is the
 * conversations inbox (ABF-119) — this screen is reached from its "new
 * message" link, and shows the list of other members in the user's own
 * cell (group+sector) — click a name to open the chat.
 *
 * Also hosts a debounced by-name search over the same cell (ABF-115) —
 * typing 2+ characters searches instead of browsing the full list. Below
 * 2 characters, no request is made at all (the backend also rejects it
 * with 422, but that's defense-in-depth, not the primary gate).
 */

import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TranslocoModule } from '@jsverse/transloco';
import { catchError, debounceTime, distinctUntilChanged, of, switchMap } from 'rxjs';

import { UserPublic } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { errorKeyFrom } from '../../../core/utils/error-key.util';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

const MIN_SEARCH_LENGTH = 2;

@Component({
  selector: 'app-new-message',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslocoModule,
    LoadingSpinnerComponent,
    ErrorDisplayComponent,
  ],
  templateUrl: './new-message.component.html',
  styleUrl: './new-message.component.scss',
})
export class NewMessageComponent implements OnInit {
  private readonly forumService = inject(ForumService);
  private readonly destroyRef = inject(DestroyRef);

  members = signal<UserPublic[]>([]);
  isLoading = signal(false);
  hasError = signal(false);
  loadErrorKey = signal('errors.generic');

  searchControl = new FormControl('', { nonNullable: true });
  searchResults = signal<UserPublic[]>([]);
  isSearching = signal(false);
  searchError = signal(false);
  searchErrorKey = signal('errors.generic');
  /** True once a real (>=2 char) search has completed — distinguishes "not enough chars yet" from "searched, zero hits". */
  hasSearched = signal(false);
  /** True while the query is >=2 chars — hides the full member list so a match isn't shown twice. */
  isSearchActive = signal(false);

  /** Raw (undebounced) typed length, just to drive the "type 2+ chars" hint below. */
  private readonly queryLength = signal(0);
  /** Only nag about the 2-char minimum once they've started typing but haven't reached it yet. */
  showMinCharsHint = computed(
    () => this.queryLength() > 0 && this.queryLength() < MIN_SEARCH_LENGTH,
  );

  ngOnInit(): void {
    this.loadMembers();
    this.watchSearch();
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

  private watchSearch(): void {
    this.searchControl.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((raw) => this.queryLength.set(raw.trim().length));

    this.searchControl.valueChanges
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap((raw) => {
          const query = raw.trim();
          if (query.length < MIN_SEARCH_LENGTH) {
            this.isSearchActive.set(false);
            this.searchResults.set([]);
            this.hasSearched.set(false);
            this.searchError.set(false);
            this.isSearching.set(false);
            return of(null);
          }

          this.isSearchActive.set(true);
          this.isSearching.set(true);
          this.searchError.set(false);
          return this.forumService.searchUsers(query).pipe(
            catchError((err) => {
              this.searchError.set(true);
              this.searchErrorKey.set(errorKeyFrom(err));
              this.isSearching.set(false);
              return of(null);
            }),
          );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((results) => {
        if (results === null) {
          return;
        }
        this.searchResults.set(results);
        this.hasSearched.set(true);
        this.isSearching.set(false);
      });
  }
}
