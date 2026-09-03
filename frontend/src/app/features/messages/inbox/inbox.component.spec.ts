import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { InboxComponent } from './inbox.component';
import type { ConversationList, ConversationSummary } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { translocoTesting } from '../../../../testing/transloco-testing';

function makeConversation(overrides: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    other_user: { id: 'user-1', first_name: 'שרה', last_name: 'לוי' },
    last_message_preview: 'הי, מה שלומך?',
    last_message_at: '2026-08-01T10:00:00Z',
    unread_count: 0,
    ...overrides,
  };
}

function makeList(
  items: ConversationSummary[],
  overrides: Partial<ConversationList> = {},
): ConversationList {
  return { items, total: items.length, page: 1, page_size: 20, ...overrides };
}

describe('InboxComponent', () => {
  let fixture: ComponentFixture<InboxComponent>;
  let component: InboxComponent;
  let forumServiceMock: { getInbox: ReturnType<typeof vi.fn> };

  function setup(): void {
    TestBed.configureTestingModule({
      imports: [InboxComponent, translocoTesting()],
      providers: [provideRouter([]), { provide: ForumService, useValue: forumServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(InboxComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  it('loads conversations on init', () => {
    forumServiceMock = { getInbox: vi.fn().mockReturnValue(of(makeList([makeConversation()]))) };
    setup();

    expect(component.isLoading()).toBe(false);
    expect(component.hasError()).toBe(false);
    expect(component.conversations().length).toBe(1);
  });

  it('sets hasError when loading fails', () => {
    forumServiceMock = {
      getInbox: vi.fn().mockReturnValue(throwError(() => ({ status: 500 }))),
    };
    setup();

    expect(component.hasError()).toBe(true);
    expect(component.isLoading()).toBe(false);
  });

  it('shows the empty state when there are no conversations yet', () => {
    forumServiceMock = { getInbox: vi.fn().mockReturnValue(of(makeList([]))) };
    setup();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('עדיין אין לך שיחות');
  });

  it('renders a link to each conversation with name, preview and an unread badge', () => {
    forumServiceMock = {
      getInbox: vi.fn().mockReturnValue(of(makeList([makeConversation({ unread_count: 3 })]))),
    };
    setup();

    const el = fixture.nativeElement as HTMLElement;
    const link = el.querySelector('a.inbox__item');
    expect(link?.getAttribute('href')).toBe('/messages/user-1');
    expect(link?.textContent).toContain('שרה');
    expect(link?.textContent).toContain('הי, מה שלומך?');
    expect(el.querySelector('.inbox__badge')?.textContent?.trim()).toBe('3');
  });

  it('gives each conversation link an accessible name that mentions the unread count', () => {
    forumServiceMock = {
      getInbox: vi.fn().mockReturnValue(of(makeList([makeConversation({ unread_count: 2 })]))),
    };
    setup();

    const link = (fixture.nativeElement as HTMLElement).querySelector('a.inbox__item');
    expect(link?.getAttribute('aria-label')).toContain('2');
  });

  it('hides pagination controls when there is only one page', () => {
    forumServiceMock = { getInbox: vi.fn().mockReturnValue(of(makeList([makeConversation()]))) };
    setup();

    expect((fixture.nativeElement as HTMLElement).querySelector('.inbox__pagination')).toBeNull();
  });

  it('shows pagination controls and advances the page on next', () => {
    forumServiceMock = {
      getInbox: vi
        .fn()
        .mockReturnValue(of(makeList([makeConversation()], { total: 25, page: 1, page_size: 20 }))),
    };
    setup();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.inbox__pagination')).not.toBeNull();

    (el.querySelectorAll('.inbox__pagination button')[1] as HTMLButtonElement).click();

    expect(forumServiceMock.getInbox).toHaveBeenCalledWith(2, 20);
  });

  it('ignores a stale response that resolves after a newer page request', () => {
    const page1$ = new Subject<ConversationList>();
    const page2$ = new Subject<ConversationList>();
    forumServiceMock = {
      getInbox: vi.fn((page: number) => (page === 1 ? page1$ : page2$)),
    };
    setup();
    page1$.next(
      makeList([makeConversation({ other_user: { id: 'p1', first_name: 'א', last_name: 'ב' } })], {
        total: 25,
      }),
    );
    fixture.detectChanges();

    (
      (fixture.nativeElement as HTMLElement).querySelectorAll(
        '.inbox__pagination button',
      )[1] as HTMLButtonElement
    ).click(); // triggers page 2 while nothing here resolves it yet

    // The newer (page 2) request resolves first...
    page2$.next(
      makeList([makeConversation({ other_user: { id: 'p2', first_name: 'ג', last_name: 'ד' } })], {
        page: 2,
        total: 25,
      }),
    );
    // ...then the older (page 1) request finally resolves, late — must be ignored.
    page1$.next(
      makeList(
        [makeConversation({ other_user: { id: 'p1-late', first_name: 'ה', last_name: 'ו' } })],
        {
          total: 25,
        },
      ),
    );

    expect(component.conversations().map((c) => c.other_user.id)).toEqual(['p2']);
  });
});
