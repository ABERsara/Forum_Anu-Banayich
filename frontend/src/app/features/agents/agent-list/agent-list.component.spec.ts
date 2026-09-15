/**
 * The AI agent catalog.
 *
 * Three things are worth holding here. That the screen shows what the server
 * returned and nothing else — the acceptance criterion is "only the domains
 * that come back for the logged-in user", and a screen that quietly filtered or
 * cached would pass a looser test. That each of the four states (loading,
 * failed, empty, populated) is distinguishable, because "no agents for you" and
 * "the request failed" are different things to be told. And the `i18n` block
 * CONTRIBUTING §6 asks of every new screen — including the one thing a text
 * sweep cannot judge on its own, which is that an agent's own name stays in
 * Hebrew in English, because it is content the association wrote.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AgentListComponent } from './agent-list.component';
import { ProfessionalDomain } from '../../../core/constants';
import type { AgentDomain } from '../../../core/models';
import { AgentService } from '../../../core/services/agent.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

const RIGHTS: AgentDomain = {
  id: 'domain-rights',
  name: 'Single-parent rights',
  description: 'Benefits and entitlements for single-parent families',
  professional_domain: ProfessionalDomain.LAWYER,
};

const ESTATES: AgentDomain = {
  id: 'domain-estates',
  name: 'Estates',
  description: 'Wills, inheritance and probate',
  professional_domain: ProfessionalDomain.ACCOUNTANT,
};

/**
 * An agent whose name and description are in Hebrew — which is how the
 * association actually writes them.
 *
 * Kept apart from the two above because the English sweep has to be able to
 * tell "a key nobody migrated" from "content, correctly left alone".
 */
const HEBREW_DOMAIN: AgentDomain = {
  id: 'domain-he',
  name: 'זכויות חד-הוריות',
  description: 'מידע על זכויות והטבות למשפחות חד-הוריות',
  professional_domain: ProfessionalDomain.LAWYER,
};

describe('AgentListComponent', () => {
  let fixture: ComponentFixture<AgentListComponent>;
  let agentServiceMock: { getDomains: ReturnType<typeof vi.fn> };

  async function render(
    getDomains = vi.fn().mockReturnValue(of([RIGHTS, ESTATES])),
  ): Promise<void> {
    TestBed.resetTestingModule();
    agentServiceMock = { getDomains };

    await TestBed.configureTestingModule({
      imports: [AgentListComponent, translocoTesting()],
      providers: [{ provide: AgentService, useValue: agentServiceMock }, provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(AgentListComponent);
    fixture.detectChanges();
  }

  function root(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return root().textContent ?? '';
  }

  function cards(): HTMLElement[] {
    return [...root().querySelectorAll<HTMLElement>('.agent-card')];
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  describe('the catalog', () => {
    it('shows exactly the agents the server returned, in that order', async () => {
      await render();

      expect(agentServiceMock.getDomains).toHaveBeenCalledTimes(1);
      expect(
        cards().map((card) => card.querySelector('.agent-card__name')!.textContent!.trim()),
      ).toEqual(['Single-parent rights', 'Estates']);
    });

    it('names the discipline behind each agent through the shared label map', async () => {
      await render();

      // 'constants.professional_domain.lawyer' — ABF-127's map, not a key of
      // this module's own.
      expect(cards()[0].querySelector('.agent-card__field')!.textContent).toContain('עו"ד');
      expect(cards()[1].querySelector('.agent-card__field')!.textContent).toContain('רואה חשבון');
    });

    it('opens the chat for the agent whose card was clicked', async () => {
      await render();

      const link = cards()[1].querySelector('a')!;
      expect(link.getAttribute('href')).toBe('/agents/domain-estates/chat');
    });

    /**
     * On a page of identical links, "Open a conversation" five times over tells
     * a reader listing them nothing (WCAG 2.4.4).
     */
    it('gives each link an accessible name that says which agent it opens', async () => {
      await render();

      expect(cards()[0].querySelector('a')!.getAttribute('aria-label')).toBe(
        'כניסה לשיחה – Single-parent rights',
      );
    });
  });

  describe('the states it can be in', () => {
    /**
     * A Subject that is never fed, so the request is genuinely still open.
     * `of([])` would have completed before the first change detection and
     * tested the empty state instead.
     */
    it('shows the spinner while the catalog is in flight, and no empty message', async () => {
      const pending = new Subject<AgentDomain[]>();
      await render(vi.fn().mockReturnValue(pending));

      expect(fixture.componentInstance.isLoading()).toBe(true);
      expect(root().querySelector('app-loading-spinner')).toBeTruthy();
      // The member must not be told "no agents" while the answer is on its way.
      expect(text()).not.toContain('אין כרגע סוכנים זמינים עבורך.');

      pending.next([RIGHTS]);
      fixture.detectChanges();

      expect(root().querySelector('app-loading-spinner')).toBeNull();
      expect(cards()).toHaveLength(1);
    });

    it('tells the member the catalog is empty rather than showing nothing', async () => {
      await render(vi.fn().mockReturnValue(of([])));

      expect(text()).toContain('אין כרגע סוכנים זמינים עבורך.');
      expect(cards()).toHaveLength(0);
    });

    it('shows our own message when the request failed with no explanation', async () => {
      await render(vi.fn().mockReturnValue(throwError(() => ({ status: 500 }))));

      expect(text()).toContain('שגיאה בטעינת רשימת הסוכנים');
      // Not the empty-catalog line: a failure is not "you have no agents".
      expect(text()).not.toContain('אין כרגע סוכנים זמינים עבורך.');
    });

    /**
     * Since ABF-137 the API writes its own sentence in `detail`. It is shown as
     * it came — it is the one thing our generic line cannot say, which is why.
     */
    it("shows the server's own sentence when it sent one", async () => {
      await render(
        vi
          .fn()
          .mockReturnValue(throwError(() => ({ error: { detail: 'אין לך הרשאה לצפות בקטלוג.' } }))),
      );

      expect(text()).toContain('אין לך הרשאה לצפות בקטלוג.');
      expect(text()).not.toContain('שגיאה בטעינת רשימת הסוכנים');
    });
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as the screen was written', async () => {
      await render();

      expect(root().querySelector('h1')!.textContent!.trim()).toBe('סוכני AI');
      expect(text()).toContain('לשאלה אישית אפשר תמיד לפנות לאיש מקצוע');
      expect(text()).toContain('כניסה לשיחה');
    });

    it('leaves no Hebrew in the chrome once the language is English', async () => {
      await render();

      switchToEnglish();

      expect(root().querySelector('h1')!.textContent!.trim()).toBe('AI agents');
      expect(text()).toContain('Open a conversation');
      expect(text()).toContain('Lawyer');
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The exception the sweep above must not be read as forbidding: an agent's
     * name and description are written by the association and are content, so
     * they stay as they came in either language — the rule a professional's own
     * description already follows.
     */
    it("leaves the agent's own words alone in English", async () => {
      await render(vi.fn().mockReturnValue(of([HEBREW_DOMAIN])));

      switchToEnglish();

      expect(text()).toContain('זכויות חד-הוריות');
      expect(text()).toContain('מידע על זכויות והטבות למשפחות חד-הוריות');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await render();

      expect(root().querySelector('.agent-list')!.hasAttribute('dir')).toBe(false);
    });
  });
});
