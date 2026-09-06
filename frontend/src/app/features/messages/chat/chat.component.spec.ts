import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ChatComponent } from './chat.component';
import { AccountStatus, Sector, UserRole, UserType } from '../../../core/constants';
import type { DirectMessage, UserProfile, UserPublic } from '../../../core/models';
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

function makeMessage(overrides: Partial<DirectMessage> = {}): DirectMessage {
  return {
    id: 'msg-1',
    sender: { id: 'me-1', first_name: 'שרה', last_name: 'לוי' },
    recipient: { id: 'other-1', first_name: 'רבקה', last_name: 'כהן' },
    content: 'שלום',
    is_read: false,
    created_at: '2026-08-01T10:00:00',
    ...overrides,
  };
}

const OTHER_MEMBER: UserPublic = { id: 'other-1', first_name: 'רבקה', last_name: 'כהן' };

/**
 * A message whose body carries no Hebrew, and the member who sent it.
 *
 * What someone typed and what they are called are user-generated content —
 * never translated (ABF-130). Feeding Latin content to the `HEBREW` sweeps
 * below keeps them pointed at our own copy, which is the thing they are meant
 * to guard.
 */
function makeLatinMessage(overrides: Partial<DirectMessage> = {}): DirectMessage {
  return makeMessage({ content: 'Hi, how are you?', ...overrides });
}

const LATIN_MEMBER: UserPublic = { id: 'other-1', first_name: 'Rivka', last_name: 'Cohen' };

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

  beforeEach(() => {
    forumServiceMock = {
      getConversation: vi.fn().mockReturnValue(of([makeMessage()])),
      sendMessage: vi.fn().mockReturnValue(of(makeMessage({ id: 'msg-2', content: 'הי!' }))),
      getCellMembers: vi.fn().mockReturnValue(of([OTHER_MEMBER])),
    };
  });

  it('loads the conversation with the other user on init', () => {
    setup();

    expect(forumServiceMock.getConversation).toHaveBeenCalledWith('me-1', 'other-1');
    expect(component.messages().length).toBe(1);
    expect(component.isLoading()).toBe(false);
  });

  it('resolves the other member name from the cell members list', () => {
    setup();

    expect(component.otherUserName()).toBe('רבקה כהן');
  });

  it('sets hasError when loading the conversation fails', () => {
    forumServiceMock.getConversation.mockReturnValue(throwError(() => ({ status: 500 })));
    setup();

    expect(component.hasError()).toBe(true);
    expect(component.isLoading()).toBe(false);
  });

  it('shows the empty state when there are no messages yet', () => {
    forumServiceMock.getConversation.mockReturnValue(of([]));
    setup();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('עדיין אין הודעות');
  });

  it('identifies own messages by sender id', () => {
    setup();

    expect(
      component.isMyMessage(makeMessage({ sender: { id: 'me-1', first_name: '', last_name: '' } })),
    ).toBe(true);
    expect(
      component.isMyMessage(
        makeMessage({ sender: { id: 'other-1', first_name: '', last_name: '' } }),
      ),
    ).toBe(false);
  });

  describe('sendMessage', () => {
    it('does nothing for blank input', () => {
      setup();

      component.newMessage = '   ';
      component.sendMessage();

      expect(forumServiceMock.sendMessage).not.toHaveBeenCalled();
    });

    it('sends the trimmed content, appends the result, and clears the input', () => {
      setup();

      component.newMessage = '  הי!  ';
      component.sendMessage();

      expect(forumServiceMock.sendMessage).toHaveBeenCalledWith({
        recipient_id: 'other-1',
        content: 'הי!',
      });
      expect(component.messages().length).toBe(2);
      expect(component.newMessage).toBe('');
      expect(component.isSending()).toBe(false);
    });

    it('sets sendError and keeps the draft on failure', () => {
      forumServiceMock.sendMessage.mockReturnValue(throwError(() => ({ status: 403 })));
      setup();

      component.newMessage = 'הי!';
      component.sendMessage();

      expect(component.sendError()).toBe(true);
      expect(component.newMessage).toBe('הי!');
      expect(component.isSending()).toBe(false);
    });
  });

  function root(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return root().textContent ?? '';
  }

  function heading(): string {
    return root().querySelector('h1')!.textContent!.trim();
  }

  function backLink(): string {
    return root().querySelector('.chat__header a')!.textContent!.trim();
  }

  function composerLabel(): string {
    return root().querySelector('.chat__composer-label')!.textContent!.trim();
  }

  function composerInput(): HTMLInputElement {
    return root().querySelector('#chat-new-message') as HTMLInputElement;
  }

  function sendButton(): string {
    return root().querySelector('.chat__composer-row button')!.textContent!.trim();
  }

  function bubbleClasses(): string[][] {
    return [...root().querySelectorAll('li.chat__message')].map((li) => [...li.classList]);
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  /**
   * This screen was written against Transloco from the start (ABF-118), so
   * ABF-135 had no Hebrew here to replace. What it did not have is the half of
   * the migration that outlives the commit: nothing failed if a key went
   * missing from `he.json`, if the Hebrew copy drifted from what shipped, or
   * if the English screen came back with a Hebrew word still in it. These
   * assertions are that guard, and they are the ticket's proof of execution.
   */
  describe('i18n', () => {
    it('reads in Hebrew exactly as it did before the keys went in', () => {
      setup();

      expect(backLink()).toBe('→ חזרה לתיבה');
      expect(composerLabel()).toBe('הודעה חדשה');
      expect(composerInput().placeholder).toBe('כתבו הודעה...');
      expect(sendButton()).toBe('שלח');
    });

    /** The other member's name is the heading; the key only fills in for it. */
    it('falls back to the generic title when the name lookup finds nobody', () => {
      forumServiceMock.getCellMembers.mockReturnValue(of([]));
      setup();

      expect(heading()).toBe('שיחה');

      switchToEnglish();

      expect(heading()).toBe('Conversation');
    });

    it('leaves no Hebrew on the page in English', () => {
      forumServiceMock.getConversation.mockReturnValue(of([makeLatinMessage()]));
      forumServiceMock.getCellMembers.mockReturnValue(of([LATIN_MEMBER]));
      setup();

      switchToEnglish();

      expect(heading()).toBe('Rivka Cohen');
      expect(backLink()).toBe('← Back to inbox');
      expect(composerLabel()).toBe('New message');
      expect(sendButton()).toBe('Send');
      // A placeholder is an attribute, so the sweep below cannot see it.
      expect(composerInput().placeholder).toBe('Write a message...');
      expect(composerInput().placeholder).not.toMatch(HEBREW);
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the empty state in English', () => {
      forumServiceMock.getConversation.mockReturnValue(of([]));
      forumServiceMock.getCellMembers.mockReturnValue(of([LATIN_MEMBER]));
      setup();

      switchToEnglish();

      expect(text()).toContain('No messages yet. Write a message to get started.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the page while the conversation is still loading', () => {
      forumServiceMock.getConversation.mockReturnValue(NEVER);
      forumServiceMock.getCellMembers.mockReturnValue(of([LATIN_MEMBER]));
      setup();
      expect(text()).toContain('טוען הודעות...');

      switchToEnglish();

      expect(root().querySelector('app-loading-spinner')).toBeTruthy();
      expect(text()).toContain('Loading messages...');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders a load failure in the new language', () => {
      forumServiceMock.getConversation.mockReturnValue(throwError(() => ({ status: 500 })));
      forumServiceMock.getCellMembers.mockReturnValue(of([LATIN_MEMBER]));
      setup();
      expect(text()).toContain('אירעה שגיאה. נסו שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong. Please try again.');
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The one failure the server names itself: `detail` comes back as a key
     * (`errors.dm_forbidden`, see error-key.util.ts), so the send error is
     * translated on both sides of the switch like any other line of copy.
     */
    it('re-renders a send failure in the new language', () => {
      forumServiceMock.getConversation.mockReturnValue(of([makeLatinMessage()]));
      forumServiceMock.getCellMembers.mockReturnValue(of([LATIN_MEMBER]));
      forumServiceMock.sendMessage.mockReturnValue(
        throwError(() => ({ error: { detail: 'errors.dm_forbidden' } })),
      );
      setup();

      component.newMessage = 'Hi!';
      component.sendMessage();
      fixture.detectChanges();
      expect(text()).toContain('אין לך הרשאה לשלוח או לצפות בהודעה זו.');

      switchToEnglish();

      expect(text()).toContain("You don't have permission to send or view this message.");
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The direction half of the acceptance criteria. Nothing in this screen
     * pins a side: `--mine` / `--theirs` carry `justify-content: flex-end` /
     * `flex-start`, which are direction-relative, so the bubbles follow
     * `<html dir>` (LocaleService) instead of a hardcoded right or left. The
     * `HEBREW` sweeps above cannot see CSS — a screen can read in perfect
     * English and still be laid out right-to-left — so the classes that carry
     * the flip are asserted directly.
     */
    it('sides each bubble with a direction-relative class, not a fixed edge', () => {
      forumServiceMock.getConversation.mockReturnValue(
        of([
          makeLatinMessage(),
          makeLatinMessage({
            id: 'msg-3',
            sender: { id: 'other-1', first_name: 'Rivka', last_name: 'Cohen' },
          }),
        ]),
      );
      setup();

      expect(bubbleClasses()).toEqual([
        ['chat__message', 'chat__message--mine'],
        ['chat__message', 'chat__message--theirs'],
      ]);
    });
  });
});
