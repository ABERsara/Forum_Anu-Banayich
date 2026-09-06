import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { InboxComponent } from './inbox.component';
import type { ConversationList, ConversationSummary } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

function makeConversation(overrides: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    other_user: { id: 'user-1', first_name: 'שרה', last_name: 'לוי' },
    last_message_preview: 'הי, מה שלומך?',
    last_message_at: '2026-08-01T10:00:00Z',
    unread_count: 0,
    ...overrides,
  };
}

/**
 * A conversation whose participant and preview carry no Hebrew.
 *
 * A name and the last thing someone typed are user-generated content — never
 * translated (ABF-130). Feeding Latin content to the `HEBREW` sweeps below
 * keeps them pointed at our own copy, which is the thing they are meant to
 * guard.
 */
function makeLatinConversation(overrides: Partial<ConversationSummary> = {}): ConversationSummary {
  return makeConversation({
    other_user: { id: 'user-1', first_name: 'Sarah', last_name: 'Levi' },
    last_message_preview: 'Hi, how are you?',
    ...overrides,
  });
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

  function root(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return root().textContent ?? '';
  }

  function heading(): string {
    return root().querySelector('h1')!.textContent!.trim();
  }

  function newLink(): string {
    return root().querySelector('.inbox__new-link')!.textContent!.trim();
  }

  /** The conversation link's accessible name — an attribute, not page text. */
  function ariaLabel(): string {
    return root().querySelector('a.inbox__item')!.getAttribute('aria-label')!;
  }

  /** Previous / "page N of M" / next, in reading order. */
  function paginationLabels(): string[] {
    return [...root().querySelectorAll('.inbox__pagination > *')].map((el) =>
      el.textContent!.replace(/\s+/g, ' ').trim(),
    );
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  /**
   * This screen was written against Transloco from the start (ABF-119), so
   * ABF-135 had no Hebrew here to replace. What it did not have is the half of
   * the migration that outlives the commit: nothing failed if a key went
   * missing from `he.json`, if the Hebrew copy drifted from what shipped, or
   * if the English screen came back with a Hebrew word still in it. These
   * assertions are that guard, and they are the ticket's proof of execution.
   */
  describe('i18n', () => {
    it('reads in Hebrew exactly as it did before the keys went in', () => {
      forumServiceMock = {
        getInbox: vi
          .fn()
          .mockReturnValue(of(makeList([makeConversation({ unread_count: 2 })], { total: 25 }))),
      };
      setup();

      expect(heading()).toBe('התיבה שלי');
      expect(newLink()).toBe('+ שיחה חדשה');
      expect(ariaLabel()).toBe('שיחה עם שרה לוי, 2 הודעות שלא נקראו');
      expect(paginationLabels()).toEqual(['הקודם', 'עמוד 1 מתוך 2', 'הבא']);
    });

    it('drops the unread count from the accessible name when nothing is unread', () => {
      forumServiceMock = {
        getInbox: vi.fn().mockReturnValue(of(makeList([makeConversation({ unread_count: 0 })]))),
      };
      setup();

      expect(ariaLabel()).toBe('שיחה עם שרה לוי');
    });

    it('leaves no Hebrew on the page in English', () => {
      forumServiceMock = {
        getInbox: vi
          .fn()
          .mockReturnValue(
            of(makeList([makeLatinConversation({ unread_count: 2 })], { total: 25 })),
          ),
      };
      setup();

      switchToEnglish();

      expect(heading()).toBe('My inbox');
      expect(newLink()).toBe('+ New message');
      expect(paginationLabels()).toEqual(['Previous', 'Page 1 of 2', 'Next']);
      // textContent cannot see an aria-label, so the sweep below would miss a
      // screen reader still being read to in Hebrew. Asserted on its own.
      expect(ariaLabel()).toBe('Conversation with Sarah Levi, 2 unread messages');
      expect(ariaLabel()).not.toMatch(HEBREW);
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the empty state in English', () => {
      forumServiceMock = { getInbox: vi.fn().mockReturnValue(of(makeList([]))) };
      setup();

      switchToEnglish();

      expect(text()).toContain("You don't have any conversations yet.");
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the page while the list is still loading', () => {
      forumServiceMock = { getInbox: vi.fn().mockReturnValue(NEVER) };
      setup();
      expect(text()).toContain('טוען שיחות...');

      switchToEnglish();

      expect(root().querySelector('app-loading-spinner')).toBeTruthy();
      expect(text()).toContain('Loading conversations...');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders the failure copy in the new language', () => {
      forumServiceMock = {
        getInbox: vi.fn().mockReturnValue(throwError(() => ({ status: 500 }))),
      };
      setup();
      expect(text()).toContain('אירעה שגיאה. נסו שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong. Please try again.');
      expect(text()).not.toMatch(HEBREW);
    });
  });
});
