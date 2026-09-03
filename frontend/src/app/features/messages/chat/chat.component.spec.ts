import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ChatComponent } from './chat.component';
import { AccountStatus, Sector, UserRole, UserType } from '../../../core/constants';
import type {
  ConversationMessagesPage,
  DirectMessage,
  DirectMessageSendResult,
  UserProfile,
  UserPublic,
} from '../../../core/models';
import { AuthService } from '../../../core/services/auth.service';
import { ForumService } from '../../../core/services/forum.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

const ME: UserProfile = {
  id: 'me-1',
  first_name: 'שרה',
  last_name: 'לוי',
  email: 'sarah@example.com',
  role: UserRole.USER,
  user_type: UserType.WIDOW,
  sector: Sector.HASIDIC,
  birth_date: '1985-03-15',
  account_status: AccountStatus.ACTIVE,
  created_at: '2026-06-01T00:00:00',
};

const ME_PUBLIC: UserPublic = { id: 'me-1', first_name: 'שרה', last_name: 'לוי' };
const OTHER: UserPublic = { id: 'other-1', first_name: 'רבקה', last_name: 'כהן' };

function makeMessage(overrides: Partial<DirectMessage> = {}): DirectMessage {
  return {
    id: 'msg-1',
    sender: ME_PUBLIC,
    recipient: OTHER,
    content: 'שלום',
    read_at: null,
    created_at: '2026-08-01T10:00:00',
    ...overrides,
  };
}

/**
 * A message whose *content* has no Hebrew in it.
 *
 * The `not.toMatch(HEBREW)` scan cannot tell our copy from a user's words
 * (CONTRIBUTING §6, ABF-130), so the fixture it runs over is Latin and the
 * scan stays aimed at the interface. A separate test below asserts the
 * opposite for Hebrew content.
 */
function makeLatinMessage(overrides: Partial<DirectMessage> = {}): DirectMessage {
  return makeMessage({
    content: 'Shalom',
    sender: { id: 'me-1', first_name: 'Sarah', last_name: 'Levi' },
    recipient: { id: 'other-1', first_name: 'Rivka', last_name: 'Cohen' },
    ...overrides,
  });
}

function makePage(
  items: DirectMessage[],
  overrides: Partial<ConversationMessagesPage> = {},
): ConversationMessagesPage {
  return { items, has_more: false, next_cursor: null, ...overrides };
}

function makeSendResult(overrides: Partial<DirectMessageSendResult> = {}): DirectMessageSendResult {
  return {
    message: makeMessage({ id: 'msg-stored', content: 'הי!' }),
    pruned_message_ids: [],
    conversation_limit: 1000,
    ...overrides,
  };
}

/** Ten messages, oldest first, the way a page arrives. */
function manyMessages(count: number, prefix = 'old'): DirectMessage[] {
  return Array.from({ length: count }, (_, index) =>
    makeMessage({
      id: `${prefix}-${index}`,
      content: `${prefix} ${index}`,
      sender: OTHER,
      recipient: ME_PUBLIC,
    }),
  );
}

describe('ChatComponent', () => {
  let fixture: ComponentFixture<ChatComponent>;
  let component: ChatComponent;
  let forumServiceMock: {
    getConversation: ReturnType<typeof vi.fn>;
    sendMessage: ReturnType<typeof vi.fn>;
    getCellMembers: ReturnType<typeof vi.fn>;
  };

  function setup(): void {
    TestBed.configureTestingModule({
      imports: [ChatComponent, translocoTesting()],
      providers: [
        { provide: ForumService, useValue: forumServiceMock },
        { provide: AuthService, useValue: { currentUser: () => ME } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ userId: 'other-1' }) } },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ChatComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function query<T extends HTMLElement>(selector: string): T | null {
    return (fixture.nativeElement as HTMLElement).querySelector<T>(selector);
  }

  function queryAll(selector: string): HTMLElement[] {
    return [...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>(selector)];
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  /** jsdom does no layout, so a scroll position has to be stated outright. */
  function pretendScrolledTo(top: number): void {
    Object.defineProperty(query('.chat__log')!, 'scrollTop', {
      value: top,
      configurable: true,
    });
  }

  beforeEach(() => {
    forumServiceMock = {
      getConversation: vi.fn().mockReturnValue(of(makePage([makeMessage()]))),
      sendMessage: vi.fn().mockReturnValue(of(makeSendResult())),
      getCellMembers: vi.fn().mockReturnValue(of([OTHER])),
    };
  });

  // -------------------------------------------------------------------------
  // Opening the screen
  // -------------------------------------------------------------------------

  it('opens on the newest page — no cursor, and one page worth', () => {
    setup();

    expect(forumServiceMock.getConversation).toHaveBeenCalledWith('me-1', 'other-1', {
      limit: 50,
    });
    expect(component.messages().length).toBe(1);
    expect(component.isLoading()).toBe(false);
  });

  it('resolves the other member name from the cell members list', () => {
    setup();

    expect(component.otherUserName()).toBe('רבקה כהן');
  });

  it('still names the other person when the cell-members lookup fails', () => {
    forumServiceMock.getCellMembers.mockReturnValue(throwError(() => ({ status: 500 })));
    forumServiceMock.getConversation.mockReturnValue(
      of(makePage([makeMessage({ sender: OTHER, recipient: ME_PUBLIC })])),
    );
    setup();

    expect(component.otherUserName()).toBe('רבקה כהן');
  });

  it('shows the empty state when the conversation has no messages yet', () => {
    forumServiceMock.getConversation.mockReturnValue(of(makePage([])));
    setup();

    expect(text()).toContain('עדיין אין הודעות');
  });

  it('shows the server reason when loading fails, not a generic line', () => {
    forumServiceMock.getConversation.mockReturnValue(
      throwError(() => ({ status: 403, error: { detail: 'errors.dm_forbidden' } })),
    );
    setup();

    expect(component.loadErrorKey()).toBe('errors.dm_forbidden');
    expect(text()).toContain('אין לך הרשאה');
  });

  it('marks the messages the current user wrote as her own', () => {
    forumServiceMock.getConversation.mockReturnValue(
      of(
        makePage([
          makeMessage({ id: 'mine', sender: ME_PUBLIC, recipient: OTHER }),
          makeMessage({ id: 'theirs', sender: OTHER, recipient: ME_PUBLIC }),
        ]),
      ),
    );
    setup();

    expect(component.messages().map((m) => m.mine)).toEqual([true, false]);
    expect(queryAll('.chat__message--mine').length).toBe(1);
    expect(queryAll('.chat__message--theirs').length).toBe(1);
  });

  // -------------------------------------------------------------------------
  // Scrolling back through the history
  // -------------------------------------------------------------------------

  describe('older messages', () => {
    function setupWithHistory(): void {
      forumServiceMock.getConversation.mockReturnValue(
        of(makePage(manyMessages(3, 'newest'), { has_more: true, next_cursor: 'cursor-1' })),
      );
      setup();
      forumServiceMock.getConversation.mockReturnValue(
        of(makePage(manyMessages(3, 'older'), { has_more: true, next_cursor: 'cursor-2' })),
      );
    }

    it('asks for the page before the oldest message on screen', () => {
      setupWithHistory();

      component.loadOlder();

      expect(forumServiceMock.getConversation).toHaveBeenLastCalledWith('me-1', 'other-1', {
        limit: 50,
        before: 'cursor-1',
      });
    });

    it('puts them above what is already there, and keeps every id distinct', () => {
      setupWithHistory();

      component.loadOlder();
      fixture.detectChanges();

      const ids = component.messages().map((m) => m.id);
      expect(ids).toEqual(['older-0', 'older-1', 'older-2', 'newest-0', 'newest-1', 'newest-2']);
      expect(new Set(ids).size).toBe(ids.length);
    });

    it('carries the next cursor forward so the following page is the one after', () => {
      setupWithHistory();

      component.loadOlder();
      component.loadOlder();

      expect(forumServiceMock.getConversation).toHaveBeenLastCalledWith('me-1', 'other-1', {
        limit: 50,
        before: 'cursor-2',
      });
    });

    it('stops asking once the server says there is nothing older', () => {
      setupWithHistory();
      forumServiceMock.getConversation.mockReturnValue(
        of(makePage(manyMessages(1, 'first'), { has_more: false, next_cursor: null })),
      );
      component.loadOlder();
      const callsSoFar = forumServiceMock.getConversation.mock.calls.length;

      component.loadOlder();

      expect(forumServiceMock.getConversation.mock.calls.length).toBe(callsSoFar);
      expect(component.hasMore()).toBe(false);
    });

    it('does not fire a second request while one is still in flight', () => {
      setupWithHistory();
      // A request that never answers — the second call has to see it as still open.
      forumServiceMock.getConversation.mockReturnValue({
        pipe: () => ({ subscribe: () => ({ unsubscribe: () => undefined }) }),
      });

      component.loadOlder();
      component.loadOlder();

      expect(forumServiceMock.getConversation).toHaveBeenCalledTimes(2); // init + one
    });

    it('loads more when the reader reaches the top of the log, and not before', () => {
      setupWithHistory();
      const callsBefore = forumServiceMock.getConversation.mock.calls.length;

      pretendScrolledTo(400);
      component.onScroll();
      expect(forumServiceMock.getConversation.mock.calls.length).toBe(callsBefore);

      pretendScrolledTo(10);
      component.onScroll();
      expect(forumServiceMock.getConversation.mock.calls.length).toBe(callsBefore + 1);
    });

    it('offers a button that does the same thing, for a reader who is not scrolling', () => {
      setupWithHistory();
      const callsBefore = forumServiceMock.getConversation.mock.calls.length;

      query<HTMLButtonElement>('.chat__older-button')!.click();

      expect(forumServiceMock.getConversation.mock.calls.length).toBe(callsBefore + 1);
    });

    it('keeps the reader in the same place when content is inserted above her', () => {
      setupWithHistory();

      // The whole rule, as arithmetic: the list grew by 600px above the
      // viewport, so the scroll position has to grow by exactly that much for
      // the message under the reader's eye to stay there. jsdom performs no
      // layout, which is why this is asserted on the calculation rather than
      // on a rendered scrollTop.
      expect(component.scrollTopAfterPrepend(1000, 120, 1600)).toBe(720);
      expect(component.scrollTopAfterPrepend(1000, 0, 1600)).toBe(600);
    });

    it('reports a failure to load older messages without losing the ones on screen', () => {
      setupWithHistory();
      forumServiceMock.getConversation.mockReturnValue(throwError(() => ({ status: 500 })));

      component.loadOlder();
      fixture.detectChanges();

      expect(component.olderErrorKey()).toBe('messages.chat.load_older_failed');
      expect(component.messages().length).toBe(3);
      expect(text()).toContain('טעינת ההודעות הקודמות נכשלה');
    });

    it('announces how many older messages arrived, without reading them out', () => {
      setupWithHistory();

      component.loadOlder();
      fixture.detectChanges();

      const status = query('[role="status"].chat__sr-only')!;
      expect(status.textContent).toContain('נטענו 3 הודעות קודמות');
    });

    it('says so when the top of the conversation has been reached', () => {
      setup();

      expect(text()).toContain('זו תחילת השיחה');
    });
  });

  // -------------------------------------------------------------------------
  // Sending
  // -------------------------------------------------------------------------

  describe('send', () => {
    it('does nothing for blank input', () => {
      setup();

      component.draft.set('   ');
      component.send();

      expect(forumServiceMock.sendMessage).not.toHaveBeenCalled();
    });

    it('shows the message before the server answers, and clears the composer', () => {
      let respond: ((result: DirectMessageSendResult) => void) | undefined;
      forumServiceMock.sendMessage.mockReturnValue({
        pipe: () => ({
          subscribe: (observer: { next: (r: DirectMessageSendResult) => void }) => {
            respond = observer.next;
            return { unsubscribe: () => undefined };
          },
        }),
      });
      setup();

      component.draft.set('  הי!  ');
      component.send();
      fixture.detectChanges();

      // Still in flight: the bubble is already on screen, and says so.
      const pending = component.messages().at(-1)!;
      expect(pending.pending).toBe(true);
      expect(pending.content).toBe('הי!');
      expect(component.draft()).toBe('');
      expect(text()).toContain('בשליחה');

      respond!(makeSendResult({ message: makeMessage({ id: 'msg-stored', content: 'הי!' }) }));
      fixture.detectChanges();

      expect(component.messages().at(-1)!.id).toBe('msg-stored');
      expect(component.messages().at(-1)!.pending).toBe(false);
      expect(component.messages().length).toBe(2);
    });

    it('sends the trimmed content to the person the route names', () => {
      setup();

      component.draft.set('  הי!  ');
      component.send();

      expect(forumServiceMock.sendMessage).toHaveBeenCalledWith({
        recipient_id: 'other-1',
        content: 'הי!',
      });
    });

    it('takes the bubble back off the screen and returns the text when the send fails', () => {
      forumServiceMock.sendMessage.mockReturnValue(throwError(() => ({ status: 500 })));
      setup();
      const before = component.messages().length;

      component.draft.set('הי!');
      component.send();
      fixture.detectChanges();

      expect(component.messages().length).toBe(before);
      expect(component.draft()).toBe('הי!');
      expect(text()).toContain('שליחת ההודעה נכשלה');
    });

    it('does not overwrite a message the user has started writing since', () => {
      let fail: ((err: unknown) => void) | undefined;
      forumServiceMock.sendMessage.mockReturnValue({
        pipe: () => ({
          subscribe: (observer: { error: (err: unknown) => void }) => {
            fail = observer.error;
            return { unsubscribe: () => undefined };
          },
        }),
      });
      setup();

      component.draft.set('הראשונה');
      component.send();
      component.draft.set('כבר כותבת את הבאה');
      fail!({ status: 500 });
      fixture.detectChanges();

      expect(component.draft()).toBe('כבר כותבת את הבאה');
      expect(text()).toContain('שליחת ההודעה נכשלה');
    });

    it('shows the reason the server gave when it gave one', () => {
      forumServiceMock.sendMessage.mockReturnValue(
        throwError(() => ({ status: 403, error: { detail: 'errors.dm_forbidden' } })),
      );
      setup();

      component.draft.set('הי!');
      component.send();
      fixture.detectChanges();

      expect(component.sendErrorKey()).toBe('errors.dm_forbidden');
    });

    it('sends on Enter and stops the newline from being typed', () => {
      setup();
      const event = new KeyboardEvent('keydown', { key: 'Enter' });
      const preventDefault = vi.spyOn(event, 'preventDefault');

      component.draft.set('הי!');
      component.onEnter(event);

      expect(preventDefault).toHaveBeenCalled();
      expect(forumServiceMock.sendMessage).toHaveBeenCalled();
    });

    it('disables the send button until there is something to send', () => {
      setup();
      const button = query<HTMLButtonElement>('.chat__composer-row button')!;
      expect(button.disabled).toBe(true);

      component.draft.set('הי');
      fixture.detectChanges();

      expect(button.disabled).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // The 1,000-message cap
  // -------------------------------------------------------------------------

  describe('the storage cap', () => {
    it('says nothing when the send cost the conversation nothing', () => {
      setup();

      component.draft.set('הי!');
      component.send();
      fixture.detectChanges();

      expect(component.pruneNotice()).toBeNull();
      expect(text()).not.toContain('נמחקה כדי לפנות מקום');
    });

    it('tells the user an old message was deleted, and names the real limit', () => {
      forumServiceMock.getConversation.mockReturnValue(
        of(makePage([makeMessage({ id: 'oldest' }), makeMessage({ id: 'newer' })])),
      );
      forumServiceMock.sendMessage.mockReturnValue(
        of(makeSendResult({ pruned_message_ids: ['oldest'], conversation_limit: 1000 })),
      );
      setup();

      component.draft.set('הי!');
      component.send();
      fixture.detectChanges();

      expect(text()).toContain('השיחה הגיעה למגבלת 1,000 ההודעות');
      expect(text()).toContain('ההודעה הישנה ביותר נמחקה כדי לפנות מקום');
      expect(query('.chat__notice')!.getAttribute('role')).toBe('status');
    });

    it('takes exactly the messages the server named off the screen', () => {
      forumServiceMock.getConversation.mockReturnValue(
        of(
          makePage([
            makeMessage({ id: 'reported' }),
            makeMessage({ id: 'oldest-prunable' }),
            makeMessage({ id: 'newer' }),
          ]),
        ),
      );
      forumServiceMock.sendMessage.mockReturnValue(
        of(makeSendResult({ pruned_message_ids: ['oldest-prunable'] })),
      );
      setup();

      component.draft.set('הי!');
      component.send();
      fixture.detectChanges();

      // 'reported' is older but carries an open report, so the server kept it.
      // Trimming the top of the list by count would have removed the wrong one.
      expect(component.messages().map((m) => m.id)).toEqual(['reported', 'newer', 'msg-stored']);
    });

    it('uses the plural wording when a send dropped more than one message', () => {
      forumServiceMock.sendMessage.mockReturnValue(
        of(makeSendResult({ pruned_message_ids: ['a', 'b', 'c'] })),
      );
      setup();

      component.draft.set('הי!');
      component.send();
      fixture.detectChanges();

      expect(text()).toContain('ו-3 ההודעות הישנות ביותר נמחקו כדי לפנות מקום');
    });
  });

  // -------------------------------------------------------------------------
  // Read receipts
  // -------------------------------------------------------------------------

  describe('the read receipt', () => {
    it('says "read" once the other side has opened the conversation', () => {
      forumServiceMock.getConversation.mockReturnValue(
        of(makePage([makeMessage({ read_at: '2026-08-01T10:05:00' })])),
      );
      setup();

      expect(query('.chat__receipt')!.textContent).toContain('נקרא');
    });

    it('says "sent" until then', () => {
      forumServiceMock.getConversation.mockReturnValue(of(makePage([makeMessage()])));
      setup();

      expect(query('.chat__receipt')!.textContent).toContain('נשלח');
    });

    it('never puts a receipt on the other person’s message', () => {
      forumServiceMock.getConversation.mockReturnValue(
        of(
          makePage([
            makeMessage({ id: 'theirs', sender: OTHER, recipient: ME_PUBLIC, read_at: null }),
          ]),
        ),
      );
      setup();

      expect(query('.chat__receipt')).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // The character counter
  // -------------------------------------------------------------------------

  describe('the character counter', () => {
    it('counts what has been typed against the limit', () => {
      setup();

      component.draft.set('חמש!');
      fixture.detectChanges();

      expect(query('#chat-char-count')!.textContent).toContain('4 מתוך 2,000 תווים');
    });

    it('describes the field rather than announcing every keystroke', () => {
      setup();

      const textarea = query<HTMLTextAreaElement>('#chat-new-message')!;
      expect(textarea.getAttribute('aria-describedby')).toBe('chat-char-count');
      expect(query('#chat-char-count')!.getAttribute('role')).toBeNull();
    });

    it('announces reaching the limit, once', () => {
      setup();
      expect(query('.chat__limit')).toBeNull();

      component.draft.set('x'.repeat(2000));
      fixture.detectChanges();

      const limit = query('.chat__limit')!;
      expect(limit.getAttribute('role')).toBe('status');
      expect(limit.textContent).toContain('הגעתם למגבלת 2,000 התווים');
    });

    it('stops the browser accepting more than the server would', () => {
      setup();

      expect(query('#chat-new-message')!.getAttribute('maxlength')).toBe('2000');
    });
  });

  // -------------------------------------------------------------------------
  // Accessibility
  // -------------------------------------------------------------------------

  describe('accessibility', () => {
    it('makes the scrolling history a named region a keyboard can reach', () => {
      setup();

      const log = query('.chat__log')!;
      expect(log.getAttribute('tabindex')).toBe('0');
      expect(log.getAttribute('aria-label')).toBe('היסטוריית השיחה');
    });

    it('announces loading, empty and error through one live region', () => {
      forumServiceMock.getConversation.mockReturnValue(of(makePage([])));
      setup();

      const states = query('.chat__states')!;
      expect(states.getAttribute('aria-live')).toBe('polite');
      expect(states.getAttribute('aria-busy')).toBe('false');
      expect(states.textContent).toContain('עדיין אין הודעות');
    });

    it('marks the region busy while the history is loading', () => {
      forumServiceMock.getConversation.mockReturnValue({
        pipe: () => ({ subscribe: () => ({ unsubscribe: () => undefined }) }),
      });
      setup();
      component.isLoading.set(true);
      fixture.detectChanges();

      expect(query('.chat__states')!.getAttribute('aria-busy')).toBe('true');
      expect(text()).toContain('טוען הודעות...');
    });

    it('says who wrote each message in words, not only in colour', () => {
      forumServiceMock.getConversation.mockReturnValue(
        of(
          makePage([
            makeMessage({ id: 'mine', sender: ME_PUBLIC, recipient: OTHER }),
            makeMessage({ id: 'theirs', sender: OTHER, recipient: ME_PUBLIC }),
          ]),
        ),
      );
      setup();

      const speakers = queryAll('.chat__speaker').map((el) => el.textContent?.trim());
      expect(speakers).toEqual(['אני:', 'רבקה כהן:']);
    });

    it('gives the composer a real label and a semantic list for the messages', () => {
      setup();

      const label = query<HTMLLabelElement>('label[for="chat-new-message"]')!;
      expect(label.textContent?.trim()).toBe('הודעה חדשה');
      expect(query('ol.chat__messages')).not.toBeNull();
      expect(query('time')!.getAttribute('datetime')).toBe('2026-08-01T10:00:00');
    });
  });

  // -------------------------------------------------------------------------
  // i18n
  // -------------------------------------------------------------------------

  describe('i18n', () => {
    it('reads in Hebrew exactly as the screen did before the rebuild', () => {
      setup();

      expect(text()).toContain('→ חזרה לתיבה');
      expect(text()).toContain('רבקה כהן');
      expect(text()).toContain('שלח');
      expect(query('#chat-new-message')!.getAttribute('placeholder')).toBe('כתבו הודעה...');
    });

    it('leaves no Hebrew on the page in English', () => {
      forumServiceMock.getConversation.mockReturnValue(
        of(makePage([makeLatinMessage()], { has_more: true, next_cursor: 'c' })),
      );
      forumServiceMock.getCellMembers.mockReturnValue(
        of([{ id: 'other-1', first_name: 'Rivka', last_name: 'Cohen' }]),
      );
      setup();

      switchToEnglish();

      expect(text()).not.toMatch(HEBREW);
      expect(text()).toContain('Load older messages');
      expect(text()).toContain('Sent');
    });

    it('leaves no Hebrew on the empty, loading or failed screens either', () => {
      forumServiceMock.getConversation.mockReturnValue(of(makePage([])));
      forumServiceMock.getCellMembers.mockReturnValue(of([]));
      setup();
      switchToEnglish();
      expect(text()).not.toMatch(HEBREW);

      component.isLoading.set(true);
      fixture.detectChanges();
      expect(text()).not.toMatch(HEBREW);

      component.isLoading.set(false);
      component.loadErrorKey.set('errors.dm_forbidden');
      fixture.detectChanges();
      expect(text()).not.toMatch(HEBREW);
    });

    it('follows a language switch with an error already on the screen', () => {
      forumServiceMock.getConversation.mockReturnValue(
        throwError(() => ({ status: 403, error: { detail: 'errors.dm_forbidden' } })),
      );
      forumServiceMock.getCellMembers.mockReturnValue(of([]));
      setup();
      expect(text()).toContain('אין לך הרשאה');

      switchToEnglish();

      expect(text()).toContain("You don't have permission");
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves what people wrote to each other in the language they wrote it', () => {
      forumServiceMock.getConversation.mockReturnValue(
        of(makePage([makeMessage({ content: 'תודה רבה לך' })])),
      );
      setup();

      switchToEnglish();

      expect(text()).toContain('תודה רבה לך');
    });

    it('keeps the counter and the prune notice in step with the language', () => {
      forumServiceMock.getConversation.mockReturnValue(of(makePage([makeLatinMessage()])));
      forumServiceMock.getCellMembers.mockReturnValue(of([]));
      forumServiceMock.sendMessage.mockReturnValue(
        of(
          makeSendResult({
            message: makeLatinMessage({ id: 'msg-stored' }),
            pruned_message_ids: ['msg-1'],
          }),
        ),
      );
      setup();
      component.draft.set('Hi');
      component.send();
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('This conversation reached its 1,000-message limit');
      expect(text()).toContain('0 of 2,000 characters');
      expect(text()).not.toMatch(HEBREW);
    });
  });
});
