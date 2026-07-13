import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ForumListComponent } from './forum-list.component';
import { GroupVisibility, PostStatus, SectorVisibility } from '../../../core/constants';
import type { ForumPost, ForumPostList } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';

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
      imports: [ForumListComponent],
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
});
