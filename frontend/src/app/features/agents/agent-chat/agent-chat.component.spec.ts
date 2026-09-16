/**
 * The agent conversation screen.
 *
 * The acceptance criteria this file is here to hold, in their own words:
 * sending a question shows the agent's real answer; the disclaimer is on
 * screen throughout; a loading state stands in for the 3–8 seconds the answer
 * takes, so the screen never looks stuck; and the referral button reaches the
 * advice form with the right discipline on it.
 *
 * The send path is driven through a `Subject` rather than `of(...)`, because
 * the interesting half of this screen is the window *between* the question and
 * the answer — a mock that resolves before the first change detection tests
 * the two ends of that window and never the middle.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AgentChatComponent } from './agent-chat.component';
import { AgentMessageRole, ProfessionalDomain } from '../../../core/constants';
import type { AgentChatResponse, AgentConversation, AgentDomain } from '../../../core/models';
import { AgentService } from '../../../core/services/agent.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

/** Latin name and description, so the English sweeps below mean what they say. */
const DOMAIN: AgentDomain = {
  id: 'domain-1',
  name: 'Single-parent rights',
  description: 'Benefits and entitlements for single-parent families',
  professional_domain: ProfessionalDomain.LAWYER,
};

const QUESTION = {
  id: 'm1',
  role: AgentMessageRole.USER,
  content: 'What am I entitled to?',
  created_at: '2026-09-15T10:00:00',
};

/**
 * An answer as the server actually stores one: the agent's text, then the
 * association's standing disclaimer, which `agent_service` concatenates onto
 * every answer so it cannot be dropped. This screen replays it verbatim.
 */
const STORED_DISCLAIMER =
  'המידע שלמעלה הוא מידע כללי מתוך בסיס הידע של העמותה, ואינו מהווה ייעוץ משפטי.';

const ANSWER = {
  id: 'm2',
  role: AgentMessageRole.AGENT,
  content: `Under the 1972 act you may claim a monthly allowance.\n\n${STORED_DISCLAIMER}`,
  created_at: '2026-09-15T10:00:06',
};

const CHAT_RESPONSE: AgentChatResponse = {
  conversation_id: 'c1',
  question: QUESTION,
  answer: ANSWER,
  sources: [
    {
      title: 'National Insurance guide',
      source_name: 'Bituach Leumi',
      source_url: 'https://x.test',
    },
    { title: 'In-house summary', source_name: null, source_url: null },
  ],
};

describe('AgentChatComponent', () => {
  let fixture: ComponentFixture<AgentChatComponent>;
  let component: AgentChatComponent;
  let agentServiceMock: {
    getDomains: ReturnType<typeof vi.fn>;
    chat: ReturnType<typeof vi.fn>;
    getConversation: ReturnType<typeof vi.fn>;
  };

  interface Options {
    domains?: unknown;
    chat?: unknown;
    conversation?: unknown;
    /** What `?conversation=` carries when the member arrives. */
    openThread?: string;
    domainId?: string;
  }

  async function render(options: Options = {}): Promise<void> {
    TestBed.resetTestingModule();

    agentServiceMock = {
      getDomains: vi.fn().mockReturnValue(options.domains ?? of([DOMAIN])),
      chat: vi.fn().mockReturnValue(options.chat ?? of(CHAT_RESPONSE)),
      getConversation: vi.fn().mockReturnValue(options.conversation ?? of(undefined)),
    };

    await TestBed.configureTestingModule({
      imports: [AgentChatComponent, translocoTesting()],
      providers: [{ provide: AgentService, useValue: agentServiceMock }, provideRouter([])],
    }).compileComponents();

    if (options.openThread) {
      // The screen reads the parameter off the router's snapshot, so the URL
      // has to be in place before the component is created.
      await TestBed.inject(Router).navigate([], {
        queryParams: { conversation: options.openThread },
      });
    }

    fixture = TestBed.createComponent(AgentChatComponent);
    fixture.componentRef.setInput('domainId', options.domainId ?? DOMAIN.id);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function root(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return root().textContent ?? '';
  }

  function bubbles(): HTMLElement[] {
    return [...root().querySelectorAll<HTMLElement>('.agent-chat__bubble')];
  }

  function type(question: string): void {
    component.draft.set(question);
    fixture.detectChanges();
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  describe('opening the screen', () => {
    it('names the agent from the catalog it looked itself up in', async () => {
      await render();

      expect(agentServiceMock.getDomains).toHaveBeenCalledTimes(1);
      expect(root().querySelector('h1')!.textContent!.trim()).toBe('Single-parent rights');
      expect(text()).toContain('אפשר לשאול את הסוכן שאלה ראשונה.');
    });

    /**
     * The catalog is already filtered by group/sector, so an id missing from it
     * is either an agent that does not exist or one this member may not use.
     * The screen must not distinguish the two, and must not offer a composer.
     */
    it("refuses an agent that is not in the member's catalog, and closes the composer", async () => {
      await render({ domainId: 'someone-elses-agent' });

      expect(text()).toContain('הסוכן הזה אינו זמין עבורך.');
      expect(root().querySelector('textarea')).toBeNull();
      expect(component.isReady()).toBe(false);
    });

    it('does not load a conversation when the route names none', async () => {
      await render();

      expect(agentServiceMock.getConversation).not.toHaveBeenCalled();
    });

    it('replays the thread named in ?conversation=', async () => {
      const conversation: AgentConversation = {
        id: 'c1',
        domain_id: DOMAIN.id,
        started_at: '2026-09-15T10:00:00',
        last_message_at: '2026-09-15T10:00:06',
        messages: [QUESTION, ANSWER],
      };
      await render({ openThread: 'c1', conversation: of(conversation) });

      expect(agentServiceMock.getConversation).toHaveBeenCalledWith(DOMAIN.id, 'c1');
      expect(bubbles()).toHaveLength(2);
      expect(text()).toContain('What am I entitled to?');
    });

    /**
     * A thread that cannot be loaded is not a dead screen — the agent is still
     * there, and a new conversation can be started.
     */
    it('keeps the composer open when the old thread could not be loaded', async () => {
      await render({ openThread: 'gone', conversation: throwError(() => ({ status: 404 })) });

      expect(text()).toContain('אפשר להתחיל שיחה חדשה');
      expect(root().querySelector('textarea')).toBeTruthy();
    });
  });

  describe('asking a question', () => {
    it("shows the agent's real answer, as the server stored it", async () => {
      await render();
      type('What am I entitled to?');

      component.send();
      fixture.detectChanges();

      expect(agentServiceMock.chat).toHaveBeenCalledWith(
        DOMAIN.id,
        'What am I entitled to?',
        undefined,
      );
      expect(bubbles()).toHaveLength(2);
      expect(text()).toContain('Under the 1972 act you may claim a monthly allowance.');
    });

    /**
     * The disclaimer at the foot of the answer is part of the stored row, not
     * chrome: `agent_service` concatenates it so it cannot be dropped, and the
     * backend documents this screen as replaying the content verbatim. Nothing
     * here strips it, banner or no banner.
     */
    it('keeps the disclaimer the server stored inside the answer', async () => {
      await render();
      type('שאלה');

      component.send();
      fixture.detectChanges();

      expect(root().querySelector('.agent-chat__text:last-of-type')).toBeTruthy();
      expect(text()).toContain(STORED_DISCLAIMER);
    });

    it('carries the conversation id into the follow-up', async () => {
      await render();
      type('first');
      component.send();
      fixture.detectChanges();

      type('and roughly how much?');
      component.send();
      fixture.detectChanges();

      expect(agentServiceMock.chat).toHaveBeenLastCalledWith(
        DOMAIN.id,
        'and roughly how much?',
        'c1',
      );
    });

    /** `Router.navigate` resolves on a microtask, so the URL is read after it. */
    it('remembers the thread in the URL, so a refresh does not lose it', async () => {
      await render();
      type('first');

      component.send();
      fixture.detectChanges();
      await fixture.whenStable();

      expect(TestBed.inject(Router).url).toContain('conversation=c1');
    });

    it('lists what the answer was drawn from, link and all', async () => {
      await render();
      type('שאלה');

      component.send();
      fixture.detectChanges();

      const sources = [...root().querySelectorAll('.agent-chat__sources li')];
      expect(sources).toHaveLength(2);
      expect(sources[0].textContent).toContain('National Insurance guide');
      expect(sources[0].querySelector('a')!.getAttribute('href')).toBe('https://x.test');
      // In-house material has no publisher and no link, and still lists.
      expect(sources[1].querySelector('a')).toBeNull();
    });

    it('refuses to send an empty or whitespace-only question', async () => {
      await render();
      type('   ');

      expect(component.canSend()).toBe(false);
      component.send();

      expect(agentServiceMock.chat).not.toHaveBeenCalled();
    });
  });

  describe('the wait for an answer', () => {
    /**
     * The criterion in the ticket's own words: "a loading state instead of a
     * screen that looks stuck". Asserted in the middle of the request, which is
     * the only place it exists.
     */
    it('shows a spinner and the question while the agent is thinking', async () => {
      const answer = new Subject<AgentChatResponse>();
      await render({ chat: answer });
      type('What am I entitled to?');

      component.send();
      fixture.detectChanges();

      expect(component.isSending()).toBe(true);
      expect(root().querySelector('.agent-chat__thinking app-loading-spinner')).toBeTruthy();
      expect(text()).toContain('הסוכן מנסח תשובה...');
      // The question is on screen the moment it is sent — waiting in front of
      // a blank log is the thing this screen is not allowed to do.
      expect(bubbles()).toHaveLength(1);
      expect(root().querySelector('.agent-chat__bubble--pending')).toBeTruthy();
      // And nothing can be sent on top of it. `NgModel` applies a bound
      // `disabled` on a microtask rather than during change detection, so the
      // textarea is read after the queue drains; the submit button is a plain
      // control and is already off.
      expect(root().querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(true);
      await fixture.whenStable();
      expect(root().querySelector('textarea')!.disabled).toBe(true);

      answer.next(CHAT_RESPONSE);
      answer.complete();
      fixture.detectChanges();

      expect(component.isSending()).toBe(false);
      expect(root().querySelector('.agent-chat__thinking app-loading-spinner')).toBeNull();
      expect(root().querySelector('.agent-chat__bubble--pending')).toBeNull();
      expect(bubbles()).toHaveLength(2);
    });

    /**
     * The pending turn is replaced by the server's copy of the question rather
     * than kept: its id and timestamp are the server's, and the thread is
     * rendered from them.
     */
    it('replaces the pending question with the row the server wrote', async () => {
      await render();
      type('What am I entitled to?');

      component.send();
      fixture.detectChanges();

      const time = root().querySelector('time')!;
      expect(time.getAttribute('datetime')).toBe(QUESTION.created_at);
      expect(root().querySelector('.agent-chat__bubble--pending')).toBeNull();
    });
  });

  describe('when the question fails', () => {
    /** A 429 after eight hundred characters must not cost the member what they wrote. */
    it('takes the question off the screen and puts it back in the box', async () => {
      await render({
        chat: throwError(() => ({
          status: 429,
          error: { detail: 'הגעת למכסת ההודעות היומית לסוכנים (30 ביממה). אפשר להמשיך מחר.' },
        })),
      });
      type('שאלה ארוכה שלא הייתי רוצה להקליד שוב');

      component.send();
      fixture.detectChanges();

      expect(bubbles()).toHaveLength(0);
      expect(component.draft()).toBe('שאלה ארוכה שלא הייתי רוצה להקליד שוב');
      expect(root().querySelector('textarea')!.disabled).toBe(false);
    });

    it("shows the server's own sentence — the quota, and when it lifts", async () => {
      await render({
        chat: throwError(() => ({
          status: 429,
          error: { detail: 'הגעת למכסת ההודעות היומית לסוכנים (30 ביממה). אפשר להמשיך מחר.' },
        })),
      });
      type('שאלה');

      component.send();
      fixture.detectChanges();

      expect(text()).toContain('30 ביממה');
      expect(text()).not.toContain('שגיאה בשליחת השאלה לסוכן');
    });

    it('falls back to our own message when the server explained nothing', async () => {
      await render({ chat: throwError(() => ({ status: 0 })) });
      type('שאלה');

      component.send();
      fixture.detectChanges();

      expect(text()).toContain('שגיאה בשליחת השאלה לסוכן');
    });
  });

  describe('the disclaimer', () => {
    it('is on screen before the first question is asked', async () => {
      await render();

      expect(root().querySelector('app-disclaimer-banner')).toBeTruthy();
      expect(text()).toContain('המידע הוא כללי בלבד ואינו מהווה ייעוץ מקצועי מחייב.');
    });

    it('is still there after the answer arrives', async () => {
      await render();
      type('שאלה');

      component.send();
      fixture.detectChanges();

      expect(root().querySelector('app-disclaimer-banner')).toBeTruthy();
    });

    /**
     * Including on the screen that could not open an agent at all: a member who
     * got this far is owed the notice either way.
     */
    it('is there even when the agent could not be opened', async () => {
      await render({ domainId: 'unknown' });

      expect(root().querySelector('app-disclaimer-banner')).toBeTruthy();
    });
  });

  describe('the referral to human advice', () => {
    it("reaches the advice form with this agent's discipline on it", async () => {
      await render();

      const link = root().querySelector<HTMLAnchorElement>('.agent-chat__referral-link')!;
      expect(link.getAttribute('href')).toBe('/advice/ask?domain=lawyer');
    });

    it('carries the discipline of the agent actually being used', async () => {
      const rabbi: AgentDomain = { ...DOMAIN, professional_domain: ProfessionalDomain.RABBI };
      await render({ domains: of([rabbi]) });

      expect(
        root().querySelector<HTMLAnchorElement>('.agent-chat__referral-link')!.getAttribute('href'),
      ).toBe('/advice/ask?domain=rabbi');
    });

    /** Nothing to refer to when no agent was resolved. */
    it('is not offered when the agent could not be opened', async () => {
      await render({ domainId: 'unknown' });

      expect(root().querySelector('.agent-chat__referral-link')).toBeNull();
    });
  });

  describe('the composer', () => {
    it('counts the characters against the limit the server enforces', async () => {
      await render();
      type('a'.repeat(1000));

      expect(component.atLimit()).toBe(true);
      expect(text()).toContain('הגעת לאורך המרבי של שאלה');
      expect(root().querySelector('textarea')!.getAttribute('maxlength')).toBe('1000');
    });

    it('sends on Enter and adds a newline on Shift+Enter', async () => {
      await render();
      type('שאלה');

      component.onEnter(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true }));
      expect(agentServiceMock.chat).not.toHaveBeenCalled();

      component.onEnter(new KeyboardEvent('keydown', { key: 'Enter' }));
      expect(agentServiceMock.chat).toHaveBeenCalledTimes(1);
    });
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as the screen was written', async () => {
      await render();

      // '‹' is Bidi_Mirrored, so it turns with <html dir> on its own and stays
      // in the markup — direction.spec.ts holds the whole app to that.
      expect(root().querySelector('.agent-chat__back')!.textContent!.trim()).toBe(
        '‹ חזרה לסוכני AI',
      );
      expect(text()).toContain('הפניה לייעוץ אנושי');
      expect(text()).toContain('שליחה');
    });

    it('leaves no Hebrew in the chrome once the language is English', async () => {
      await render();

      switchToEnglish();

      expect(text()).toContain('Back to AI agents');
      expect(text()).toContain('Refer me to human advice');
      expect(text()).toContain('This information is general only');
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The exception the sweep above must not be read as forbidding. An agent's
     * answer is stored text — written in Hebrew, encrypted, and read back
     * months later — so it stays as it came, disclaimer paragraph and all.
     */
    it("leaves the agent's stored answer alone in English", async () => {
      await render();
      type('שאלה');
      component.send();
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain(STORED_DISCLAIMER);
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await render();

      expect(root().querySelector('.agent-chat')!.hasAttribute('dir')).toBe(false);
    });
  });
});
