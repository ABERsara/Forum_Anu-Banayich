import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ChatComponent } from './chat.component';
import { AccountStatus, Sector, UserRole, UserType } from '../../../core/constants';
import type { DirectMessage, UserProfile, UserPublic } from '../../../core/models';
import { AuthService } from '../../../core/services/auth.service';
import { ForumService } from '../../../core/services/forum.service';
import { translocoTesting } from '../../../../testing/transloco-testing';

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
});
