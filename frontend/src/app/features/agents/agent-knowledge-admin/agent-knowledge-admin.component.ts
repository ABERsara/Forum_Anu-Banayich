/**
 * Knowledge base admin – where a professional maintains what an agent answers
 * from (ABF-124, SPEC §12.2: "updated periodically by a professional certified
 * in the field").
 *
 * The screen offers only the domains `/agents/manageable` returns, and every
 * write is authorized again on the server by `can_manage_knowledge`, so a
 * domain id typed or kept from another session is refused there rather than
 * trusted here. Indexing is the server's job too: a saved title or content is
 * re-embedded before the response arrives, with nothing for this screen to
 * trigger.
 */

import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { Subscription } from 'rxjs';

import { PROFESSIONAL_DOMAIN_LABELS } from '../../../core/constants';
import {
  AgentDomain,
  AgentKnowledgeEntry,
  AgentKnowledgeEntryCreateRequest,
  AgentKnowledgeEntryUpdateRequest,
} from '../../../core/models';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { AgentService } from '../../../core/services/agent.service';
import { AuthService } from '../../../core/services/auth.service';
import { utcIso } from '../../../core/utils/utc-date.util';
import { ButtonComponent } from '../../../shared/components/button/button.component';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

/** Mirror TITLE_MAX_LENGTH / SOURCE_*_MAX_LENGTH in backend/app/schemas/agent.py. */
export const TITLE_MAX_LENGTH = 256;
export const SOURCE_NAME_MAX_LENGTH = 256;
export const SOURCE_URL_MAX_LENGTH = 1024;

const PAGE_SIZE = 20;

/** An absolute web address: the agent chat renders it as a link members click. */
const WEB_URL = /^https?:\/\/\S+$/i;

/** `Validators.required` accepts a field of spaces; the knowledge base should not. */
export function notBlank(control: AbstractControl): ValidationErrors | null {
  const value: unknown = control.value;
  return typeof value === 'string' && value.trim() !== '' ? null : { required: true };
}

/**
 * A confirmation this screen raised, as a key and the entry title it names —
 * kept apart so the template runs the pipe and the sentence follows a language
 * switch (CONTRIBUTING §6).
 */
interface EntryMessage {
  key: string;
  title: string;
}

@Component({
  selector: 'app-agent-knowledge-admin',
  standalone: true,
  imports: [
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
    ButtonComponent,
    ConfirmDialogComponent,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
  templateUrl: './agent-knowledge-admin.component.html',
  styleUrl: './agent-knowledge-admin.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgentKnowledgeAdminComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly agentService = inject(AgentService);
  private readonly destroyRef = inject(DestroyRef);

  /**
   * An admin reaches this screen too (by URL, for now), but not the pending
   * questions it sits next to, so the way back goes to their own dashboard.
   */
  readonly isAdmin = inject(AuthService).isAdmin;

  readonly domains = signal<AgentDomain[]>([]);
  readonly isLoadingDomains = signal(false);
  readonly domainsError = signal(false);
  readonly selectedDomainId = signal<string | null>(null);
  readonly selectedDomain = computed(
    () => this.domains().find((domain) => domain.id === this.selectedDomainId()) ?? null,
  );

  readonly entries = signal<AgentKnowledgeEntry[]>([]);
  readonly isLoadingEntries = signal(false);
  readonly entriesError = signal(false);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageCount = computed(() => Math.max(1, Math.ceil(this.total() / PAGE_SIZE)));

  /** What went wrong on save or delete, as a key of ours or the API's own sentence. */
  readonly actionError = signal<ScreenError>(NO_ERROR);
  readonly successMessage = signal<EntryMessage | null>(null);

  readonly isFormOpen = signal(false);
  /** The entry being edited; null while the form is adding a new one. */
  readonly editing = signal<AgentKnowledgeEntry | null>(null);
  readonly isSaving = signal(false);

  readonly pendingDeletion = signal<AgentKnowledgeEntry | null>(null);
  readonly isDeleting = signal(false);
  /**
   * A write in flight belongs to the domain it started on. Switching domain
   * under it would show its confirmation over the other domain's list, so the
   * picker waits for it.
   */
  readonly isBusy = computed(() => this.isSaving() || this.isDeleting());

  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;
  readonly titleMaxLength = TITLE_MAX_LENGTH;
  readonly sourceNameMaxLength = SOURCE_NAME_MAX_LENGTH;
  readonly sourceUrlMaxLength = SOURCE_URL_MAX_LENGTH;

  readonly form = this.fb.nonNullable.group({
    title: ['', [notBlank, Validators.maxLength(TITLE_MAX_LENGTH)]],
    content: ['', notBlank],
    source_name: ['', Validators.maxLength(SOURCE_NAME_MAX_LENGTH)],
    source_url: ['', [Validators.maxLength(SOURCE_URL_MAX_LENGTH), Validators.pattern(WEB_URL)]],
  });

  /** The page load in flight, so switching domain drops an answer for the old one. */
  private entriesRequest: Subscription | null = null;

  constructor() {
    this.destroyRef.onDestroy(() => this.entriesRequest?.unsubscribe());
  }

  ngOnInit(): void {
    this.isLoadingDomains.set(true);
    this.domainsError.set(false);
    this.agentService.getManageableDomains().subscribe({
      next: (domains) => {
        this.domains.set(domains);
        this.isLoadingDomains.set(false);
        if (domains.length > 0) {
          this.selectDomain(domains[0].id);
        }
      },
      error: () => {
        this.domainsError.set(true);
        this.isLoadingDomains.set(false);
      },
    });
  }

  // -------------------------------------------------------------------------
  // Domain and paging
  // -------------------------------------------------------------------------

  selectDomain(domainId: string): void {
    if (this.isBusy()) {
      return;
    }
    this.closeForm();
    this.clearMessages();
    this.selectedDomainId.set(domainId);
    this.loadEntries(1);
  }

  goToPreviousPage(): void {
    if (this.page() > 1) {
      this.loadEntries(this.page() - 1);
    }
  }

  goToNextPage(): void {
    if (this.page() < this.pageCount()) {
      this.loadEntries(this.page() + 1);
    }
  }

  /** The instant an entry was last saved, parsed as the UTC it is. */
  updatedAt(entry: AgentKnowledgeEntry): string {
    return utcIso(entry.updated_at);
  }

  // -------------------------------------------------------------------------
  // Form
  // -------------------------------------------------------------------------

  openAddForm(): void {
    this.clearMessages();
    this.editing.set(null);
    this.form.reset();
    this.isFormOpen.set(true);
  }

  openEditForm(entry: AgentKnowledgeEntry): void {
    this.clearMessages();
    this.editing.set(entry);
    this.form.reset({
      title: entry.title,
      content: entry.content,
      source_name: entry.source_name ?? '',
      source_url: entry.source_url ?? '',
    });
    this.isFormOpen.set(true);
  }

  closeForm(): void {
    this.isFormOpen.set(false);
    this.editing.set(null);
  }

  save(): void {
    const domainId = this.selectedDomainId();
    // A second submit before the first answers would create the entry twice.
    if (!domainId || this.isSaving()) {
      return;
    }
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const editing = this.editing();
    let request$;
    if (editing) {
      const changes = this.changesTo(editing);
      if (Object.keys(changes).length === 0) {
        // Nothing to write — and a PATCH with the same title would still
        // re-index the entry for nothing.
        this.closeForm();
        return;
      }
      request$ = this.agentService.updateKnowledgeEntry(domainId, editing.id, changes);
    } else {
      request$ = this.agentService.createKnowledgeEntry(domainId, this.formBody());
    }

    this.isSaving.set(true);
    this.clearMessages();
    request$.subscribe({
      next: (saved) => {
        this.successMessage.set({
          key: editing ? 'agents.knowledge.updated' : 'agents.knowledge.created',
          title: saved.title,
        });
        this.isSaving.set(false);
        this.closeForm();
        // Newest edit first: whatever was just saved now heads page one.
        this.loadEntries(1);
      },
      error: (err: HttpErrorResponse) => {
        this.actionError.set(screenErrorFrom(err, 'agents.errors.save_entry_failed'));
        this.isSaving.set(false);
      },
    });
  }

  // -------------------------------------------------------------------------
  // Delete
  // -------------------------------------------------------------------------

  requestDelete(entry: AgentKnowledgeEntry): void {
    this.clearMessages();
    this.pendingDeletion.set(entry);
  }

  cancelDelete(): void {
    this.pendingDeletion.set(null);
  }

  confirmDelete(): void {
    const entry = this.pendingDeletion();
    const domainId = this.selectedDomainId();
    // The dialog stays open until the server answers, and its confirm button
    // is not ours to disable: a double click would send a second DELETE, whose
    // 404 would show as a failure right after the first one succeeded.
    if (!entry || !domainId || this.isDeleting()) {
      return;
    }

    this.isDeleting.set(true);
    this.agentService.deleteKnowledgeEntry(domainId, entry.id).subscribe({
      next: () => {
        this.successMessage.set({ key: 'agents.knowledge.deleted', title: entry.title });
        if (this.editing()?.id === entry.id) {
          this.closeForm();
        }
        this.isDeleting.set(false);
        this.pendingDeletion.set(null);
        // If this was the last entry on its page, loadEntries() steps back.
        this.loadEntries(this.page());
      },
      error: (err: HttpErrorResponse) => {
        this.actionError.set(screenErrorFrom(err, 'agents.errors.delete_entry_failed'));
        this.isDeleting.set(false);
        this.pendingDeletion.set(null);
      },
    });
  }

  // -------------------------------------------------------------------------
  // Internals
  // -------------------------------------------------------------------------

  private loadEntries(page: number): void {
    const domainId = this.selectedDomainId();
    if (!domainId) {
      return;
    }

    this.entriesRequest?.unsubscribe();
    this.isLoadingEntries.set(true);
    this.entriesError.set(false);
    this.entriesRequest = this.agentService
      .listKnowledgeEntries(domainId, page, PAGE_SIZE)
      .subscribe({
        next: (result) => {
          // The page asked for no longer exists — its entries were deleted,
          // here or by someone else — so go to the last page that does, rather
          // than show "no content" with no pager to leave it by.
          const lastPage = Math.ceil(result.total / PAGE_SIZE);
          if (result.items.length === 0 && result.page > lastPage && lastPage >= 1) {
            this.loadEntries(lastPage);
            return;
          }
          this.entries.set(result.items);
          this.total.set(result.total);
          this.page.set(result.page);
          this.isLoadingEntries.set(false);
        },
        error: () => {
          this.entries.set([]);
          this.total.set(0);
          this.entriesError.set(true);
          this.isLoadingEntries.set(false);
        },
      });
  }

  /** The form as a create body; a blank source field means no source. */
  private formBody(): AgentKnowledgeEntryCreateRequest {
    const value = this.form.getRawValue();
    return {
      title: value.title.trim(),
      content: value.content.trim(),
      source_name: value.source_name.trim() || null,
      source_url: value.source_url.trim() || null,
    };
  }

  /**
   * Only the fields that differ from the stored entry. The server re-embeds
   * when `title` or `content` is present, so a corrected source link alone
   * must not carry them along.
   */
  private changesTo(entry: AgentKnowledgeEntry): AgentKnowledgeEntryUpdateRequest {
    const body = this.formBody();
    const changes: AgentKnowledgeEntryUpdateRequest = {};
    if (body.title !== entry.title) {
      changes.title = body.title;
    }
    if (body.content !== entry.content) {
      changes.content = body.content;
    }
    if (body.source_name !== entry.source_name) {
      changes.source_name = body.source_name;
    }
    if (body.source_url !== entry.source_url) {
      changes.source_url = body.source_url;
    }
    return changes;
  }

  private clearMessages(): void {
    this.actionError.set(NO_ERROR);
    this.successMessage.set(null);
  }
}
