/**
 * The AI agent catalog (ABF-123) — every agent this member may talk to.
 *
 * Deliberately not filtered here. `GET /agents` returns what the caller's
 * group/sector allows and nothing else, the same way a forum post is gated, so
 * a client-side filter would be a second, weaker copy of a decision the server
 * has already made. That is also why the list is fetched on every visit rather
 * than cached: a cached catalog outlives the account it was fetched for.
 *
 * The domain `name` and `description` come out of the database in Hebrew,
 * written by the association. They are content, not UI, and are rendered as
 * they came in either language — the rule a professional's own description
 * already follows in `advice-list` (CONTRIBUTING §6).
 */

import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { PROFESSIONAL_DOMAIN_LABELS } from '../../../core/constants';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { AgentDomain } from '../../../core/models';
import { AgentService } from '../../../core/services/agent.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-agent-list',
  imports: [RouterLink, TranslocoPipe, ErrorDisplayComponent, LoadingSpinnerComponent],
  templateUrl: './agent-list.component.html',
  styleUrl: './agent-list.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgentListComponent implements OnInit {
  private readonly agentService = inject(AgentService);

  readonly domains = signal<AgentDomain[]>([]);
  readonly isLoading = signal(false);
  /** Held as a key or a server sentence, never as translated text (ABF-132). */
  readonly error = signal<ScreenError>(NO_ERROR);

  /** A shared label *key* per discipline — the template pipes it (ABF-127). */
  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;

  ngOnInit(): void {
    this.isLoading.set(true);
    this.error.set(NO_ERROR);

    this.agentService.getDomains().subscribe({
      next: (domains) => {
        this.domains.set(domains);
        this.isLoading.set(false);
      },
      error: (err) => {
        this.error.set(screenErrorFrom(err, 'agents.errors.load_domains_failed'));
        this.isLoading.set(false);
      },
    });
  }
}
