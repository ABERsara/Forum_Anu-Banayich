import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { Observable, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ForumListComponent } from './forum-list.component';
import { GroupVisibility, PostStatus, SectorVisibility } from '../../../core/constants';
import type { ForumPost, ForumPostList } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

function makePost(overrides: Partial<ForumPost> = {}): ForumPost {
  return {
    id: 'p1',
    title: 'כותרת',
    content: 'תוכן',
    group_visibility: GroupVisibility.WIDOWS,
    sector_visibility: SectorVisibility.HASIDIC,
    status: PostStatus.VISIBLE,
    report_count: 0,
    author: { id: 'u1', first_name: 'שרה', last_name: 'לוי' },
    attachment_url: null,
    created_at: '2026-07-01T10:00:00',
    updated_at: '2026-07-01T10:00:00',
    ...overrides,
  };
}

/**
 * A post whose own text carries no Hebrew.
 *
 * A post's title, body and author name are user-generated content — out of
 * scope for ABF-130 and never translated. Feeding Latin content to the
 * `HEBREW` sweeps below keeps them pointed at the UI copy, which is the thing
 * they are meant to guard.
 */
function makeLatinPost(overrides: Partial<ForumPost> = {}): ForumPost {
  return makePost({
    title: 'A question about the paperwork',
    content: 'Body text',
    author: { id: 'u1', first_name: 'Sara', last_name: 'Levi' },
    ...overrides,
  });
}

function makeList(overrides: Partial<ForumPostList> = {}): ForumPostList {
  return {
    items: [makePost()],
    total: 1,
    page: 1,
    page_size: 20,
    ...overrides,
  };
}

describe('ForumListComponent', () => {
  let fixture: ComponentFixture<ForumListComponent>;
  let component: ForumListComponent;
  let forumServiceMock: { getPosts: ReturnType<typeof vi.fn> };

  beforeEach(async () => {
    forumServiceMock = {
      getPosts: vi.fn().mockReturnValue(of(makeList())),
    };

    await TestBed.configureTestingModule({
      imports: [ForumListComponent, translocoTesting()],
      providers: [provideRouter([]), { provide: ForumService, useValue: forumServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(ForumListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('loads posts on init', () => {
    expect(component.isLoading()).toBe(false);
    expect(component.hasError()).toBe(false);
    expect(component.posts().length).toBe(1);
    expect(component.total()).toBe(1);
  });

  it('sets hasError when loading fails', () => {
    forumServiceMock.getPosts.mockReturnValue(throwError(() => ({})));

    component.ngOnInit();

    expect(component.hasError()).toBe(true);
    expect(component.isLoading()).toBe(false);
  });

  it('shows the empty state when there are no posts', () => {
    forumServiceMock.getPosts.mockReturnValue(of(makeList({ items: [], total: 0 })));

    const emptyFixture = TestBed.createComponent(ForumListComponent);
    emptyFixture.detectChanges();

    const text = (emptyFixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('אין הודעות עדיין');
  });

  it('computes totalPages from total and pageSize', () => {
    forumServiceMock.getPosts.mockReturnValue(of(makeList({ total: 45, page_size: 20 })));

    component.ngOnInit();

    expect(component.totalPages()).toBe(3);
  });

  it('nextPage requests the next page when not on the last page', () => {
    forumServiceMock.getPosts.mockReturnValue(of(makeList({ total: 45, page: 1, page_size: 20 })));
    component.ngOnInit();
    forumServiceMock.getPosts.mockClear();

    component.nextPage();

    expect(forumServiceMock.getPosts).toHaveBeenCalledWith(2, 20);
  });

  it('nextPage does nothing on the last page', () => {
    forumServiceMock.getPosts.mockReturnValue(of(makeList({ total: 10, page: 1, page_size: 20 })));
    component.ngOnInit();
    forumServiceMock.getPosts.mockClear();

    component.nextPage();

    expect(forumServiceMock.getPosts).not.toHaveBeenCalled();
  });

  it('previousPage does nothing on the first page', () => {
    forumServiceMock.getPosts.mockClear();

    component.previousPage();

    expect(forumServiceMock.getPosts).not.toHaveBeenCalled();
  });

  it('previousPage requests the previous page', () => {
    forumServiceMock.getPosts.mockReturnValue(of(makeList({ total: 45, page: 2, page_size: 20 })));
    component.ngOnInit();
    forumServiceMock.getPosts.mockClear();

    component.previousPage();

    expect(forumServiceMock.getPosts).toHaveBeenCalledWith(1, 20);
  });

  it('shows a visibility badge for each post', () => {
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('אלמנות');
    expect(text).toContain('חסידי');
  });

  it('shows those badges in English under an English locale', () => {
    fixture.detectChanges();

    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Widows');
    expect(text).toContain('Hasidic');
    expect(text).not.toContain('אלמנות');
  });

  describe('i18n', () => {
    function text(): string {
      return (fixture.nativeElement as HTMLElement).textContent ?? '';
    }

    function heading(): string {
      return fixture.nativeElement.querySelector('h1').textContent.trim();
    }

    function switchToEnglish(): void {
      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();
    }

    /** Re-renders the list against a different service response. */
    function renderWith(response: Observable<ForumPostList>): void {
      forumServiceMock.getPosts.mockReturnValue(response);
      fixture = TestBed.createComponent(ForumListComponent);
      fixture.detectChanges();
    }

    it('reads in Hebrew exactly as it did before the keys went in', () => {
      expect(heading()).toBe('פורום הקהילה');
      expect(text()).toContain('+ פרסום הודעה חדשה');
      expect(text()).toContain('הקודם');
      expect(text()).toContain('עמוד 1 מתוך 1');
      expect(text()).toContain('הבא');
    });

    it('leaves no Hebrew on the page in English', () => {
      renderWith(of(makeList({ items: [makeLatinPost()] })));

      switchToEnglish();

      expect(heading()).toBe('Community forum');
      expect(text()).toContain('+ New post');
      expect(text()).toContain('Previous');
      expect(text()).toContain('Next');
      expect(text()).toContain('Widows');
      expect(text()).toContain('Hasidic');
      expect(text()).not.toMatch(HEBREW);
    });

    it('keeps the page numbers when the sentence around them changes', () => {
      renderWith(of(makeList({ items: [makeLatinPost()], total: 45, page: 2, page_size: 20 })));
      expect(text()).toContain('עמוד 2 מתוך 3');

      switchToEnglish();

      expect(text()).toContain('Page 2 of 3');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the empty state', () => {
      renderWith(of(makeList({ items: [], total: 0 })));

      switchToEnglish();

      expect(text()).toContain('No posts yet. Be the first to post!');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The failure is held as a key, so it follows the switch instead of freezing. */
    it('re-renders a load failure that is already on screen', () => {
      renderWith(throwError(() => ({})));
      expect(text()).toContain('אירעה שגיאה בטעינת הפוסטים. נסה לרענן את הדף.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong loading the posts. Please refresh the page.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Out of scope by the ticket: a post is written by a user, not by us. */
    it('leaves user-generated content in the language it was written in', () => {
      renderWith(of(makeList({ items: [makePost({ title: 'כותרת שמשתמש כתב' })] })));

      switchToEnglish();

      expect(text()).toContain('כותרת שמשתמש כתב');
      expect(text()).toContain('שרה');
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      expect(fixture.nativeElement.querySelector('.forum-list').hasAttribute('dir')).toBe(false);
    });
  });
});
