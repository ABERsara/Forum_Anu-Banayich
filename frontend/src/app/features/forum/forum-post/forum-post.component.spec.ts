import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ForumPostComponent } from './forum-post.component';
import {
  AccountStatus,
  GroupVisibility,
  PostStatus,
  Sector,
  SectorVisibility,
  UserRole,
  UserType,
} from '../../../core/constants';
import type { ForumPost, UserProfile } from '../../../core/models';
import { AuthService } from '../../../core/services/auth.service';
import { ForumService } from '../../../core/services/forum.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

function makePost(overrides: Partial<ForumPost> = {}): ForumPost {
  return {
    id: 'post-1',
    title: 'כותרת',
    content: 'תוכן ההודעה',
    group_visibility: GroupVisibility.WIDOWS,
    sector_visibility: SectorVisibility.HASIDIC,
    status: PostStatus.VISIBLE,
    report_count: 0,
    author: { id: 'author-1', first_name: 'שרה', last_name: 'לוי' },
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
    author: { id: 'author-1', first_name: 'Sara', last_name: 'Levi' },
    ...overrides,
  });
}

function makeUser(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    id: 'author-1',
    first_name: 'שרה',
    last_name: 'לוי',
    email: 'sarah@example.com',
    role: UserRole.USER,
    user_type: UserType.WIDOW,
    sector: Sector.HASIDIC,
    birth_date: '1985-03-15',
    account_status: AccountStatus.ACTIVE,
    created_at: '2026-06-01T00:00:00',
    ...overrides,
  };
}

describe('ForumPostComponent', () => {
  let fixture: ComponentFixture<ForumPostComponent>;
  let component: ForumPostComponent;
  let forumServiceMock: {
    getPost: ReturnType<typeof vi.fn>;
    deletePost: ReturnType<typeof vi.fn>;
  };
  let authServiceMock: {
    currentUser: ReturnType<typeof vi.fn>;
    isModerator: ReturnType<typeof vi.fn>;
    isAdmin: ReturnType<typeof vi.fn>;
  };
  let navigateSpy: ReturnType<typeof vi.fn>;

  function setup(
    currentUser: UserProfile | null,
    isModerator = false,
    isAdmin = false,
    post: ForumPost = makePost(),
  ): void {
    forumServiceMock = {
      getPost: vi.fn().mockReturnValue(of(post)),
      deletePost: vi.fn().mockReturnValue(of(makePost({ status: PostStatus.DELETED }))),
    };
    authServiceMock = {
      currentUser: vi.fn().mockReturnValue(currentUser),
      isModerator: vi.fn().mockReturnValue(isModerator),
      isAdmin: vi.fn().mockReturnValue(isAdmin),
    };
    navigateSpy = vi.fn();

    TestBed.configureTestingModule({
      imports: [ForumPostComponent, translocoTesting()],
      providers: [
        { provide: ForumService, useValue: forumServiceMock },
        { provide: AuthService, useValue: authServiceMock },
        { provide: Router, useValue: { navigate: navigateSpy } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ id: 'post-1' }) } },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ForumPostComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  describe('loading the post', () => {
    it('loads the post on init', () => {
      setup(makeUser());

      expect(forumServiceMock.getPost).toHaveBeenCalledWith('post-1');
      expect(component.post()?.id).toBe('post-1');
      expect(component.isLoading()).toBe(false);
    });

    it('shows a not-found message on 404', () => {
      setup(makeUser());
      forumServiceMock.getPost.mockReturnValue(throwError(() => ({ status: 404 })));

      component.ngOnInit();
      fixture.detectChanges();

      expect(component.errorKey()).toBe('forum.errors.not_found');
      expect(text()).toContain('ההודעה לא נמצאה.');
    });

    it('shows a permission message on 403', () => {
      setup(makeUser());
      forumServiceMock.getPost.mockReturnValue(throwError(() => ({ status: 403 })));

      component.ngOnInit();
      fixture.detectChanges();

      expect(component.errorKey()).toBe('forum.errors.view_forbidden');
      expect(text()).toContain('אין לך הרשאה לצפות בהודעה זו.');
    });

    it('shows a generic message on other errors', () => {
      setup(makeUser());
      forumServiceMock.getPost.mockReturnValue(throwError(() => ({ status: 500 })));

      component.ngOnInit();
      fixture.detectChanges();

      expect(component.errorKey()).toBe('forum.errors.load_post_failed');
      expect(text()).toContain('אירעה שגיאה בטעינת ההודעה. נסה לרענן את הדף.');
    });
  });

  describe('canDelete', () => {
    it('is true for the post author', () => {
      setup(makeUser({ id: 'author-1' }));

      expect(component.canDelete()).toBe(true);
    });

    it('is true for a moderator who is not the author', () => {
      setup(makeUser({ id: 'someone-else', role: UserRole.MODERATOR }), true, false);

      expect(component.canDelete()).toBe(true);
    });

    it('is true for an admin who is not the author', () => {
      setup(makeUser({ id: 'someone-else', role: UserRole.ADMIN }), false, true);

      expect(component.canDelete()).toBe(true);
    });

    it('is false for a regular user who is not the author', () => {
      setup(makeUser({ id: 'someone-else' }));

      expect(component.canDelete()).toBe(false);
    });
  });

  describe('canEdit', () => {
    it('is true for the post author', () => {
      setup(makeUser({ id: 'author-1' }));

      expect(component.canEdit()).toBe(true);
    });

    it('is false for a moderator who is not the author', () => {
      setup(makeUser({ id: 'someone-else', role: UserRole.MODERATOR }), true, false);

      expect(component.canEdit()).toBe(false);
    });

    it('is false for an admin who is not the author', () => {
      setup(makeUser({ id: 'someone-else', role: UserRole.ADMIN }), false, true);

      expect(component.canEdit()).toBe(false);
    });
  });

  describe('delete flow', () => {
    it('opens the confirm dialog on delete click', () => {
      setup(makeUser());

      component.onDeleteClick();
      fixture.detectChanges();

      expect(component.showDeleteConfirm()).toBe(true);
      expect(fixture.nativeElement.querySelector('app-confirm-dialog')).toBeTruthy();
    });

    it('closes the dialog without deleting on cancel', () => {
      setup(makeUser());
      component.onDeleteClick();

      component.onDeleteCancelled();

      expect(component.showDeleteConfirm()).toBe(false);
      expect(forumServiceMock.deletePost).not.toHaveBeenCalled();
    });

    it('deletes the post and navigates back to /forum on confirm', () => {
      setup(makeUser());
      component.onDeleteClick();

      component.onDeleteConfirmed();

      expect(forumServiceMock.deletePost).toHaveBeenCalledWith('post-1');
      expect(navigateSpy).toHaveBeenCalledWith(['/forum']);
      expect(component.showDeleteConfirm()).toBe(false);
    });

    it('shows an error and does not navigate when delete fails', () => {
      setup(makeUser());
      forumServiceMock.deletePost.mockReturnValue(throwError(() => ({ status: 500 })));
      component.onDeleteClick();

      component.onDeleteConfirmed();
      fixture.detectChanges();

      expect(component.deleteErrorKey()).toBe('forum.errors.delete_failed');
      expect(text()).toContain('אירעה שגיאה במחיקת ההודעה. נסה שוב.');
      expect(navigateSpy).not.toHaveBeenCalled();
    });
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as it did before the keys went in', () => {
      setup(makeUser(), false, false, makePost({ attachment_url: 'https://example.test/f.pdf' }));

      expect(text()).toContain('חזרה לפורום');
      expect(text()).toContain('קובץ מצורף');
      expect(text()).toContain('עריכה');
      expect(text()).toContain('מחיקה');
    });

    it('leaves no Hebrew on the page in English', () => {
      setup(
        makeUser({ first_name: 'Sara', last_name: 'Levi' }),
        false,
        false,
        makeLatinPost({ attachment_url: 'https://example.test/f.pdf' }),
      );

      switchToEnglish();

      expect(text()).toContain('Back to the forum');
      expect(text()).toContain('Attachment');
      expect(text()).toContain('Edit');
      expect(text()).toContain('Delete');
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The dialog is dumb — it renders whatever string it is handed — so a key
     * passed by mistake would land on screen verbatim. This asserts on both the
     * text that should be there and the key that should not.
     */
    it('hands the confirm dialog translated text, not raw keys', () => {
      setup(makeUser(), false, false, makeLatinPost());
      component.onDeleteClick();
      fixture.detectChanges();

      expect(text()).toContain('מחיקת הודעה');
      expect(text()).toContain('פעולה זו תמחק את ההודעה. לא ניתן לשחזר.');
      expect(text()).not.toContain('forum.delete_post');

      switchToEnglish();

      expect(text()).toContain('Delete post');
      expect(text()).toContain('This will delete the post. It cannot be undone.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The failure is held as a key, so it follows the switch instead of freezing. */
    it('re-renders a failure that is already on screen', () => {
      setup(makeUser());
      forumServiceMock.getPost.mockReturnValue(throwError(() => ({ status: 403 })));
      component.ngOnInit();
      fixture.detectChanges();
      expect(text()).toContain('אין לך הרשאה לצפות בהודעה זו.');

      switchToEnglish();

      expect(text()).toContain('You do not have permission to view this post.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Out of scope by the ticket: a post is written by a user, not by us. */
    it('leaves user-generated content in the language it was written in', () => {
      setup(makeUser());

      switchToEnglish();

      expect(text()).toContain('תוכן ההודעה');
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      setup(makeUser());

      expect(fixture.nativeElement.querySelector('.forum-post').hasAttribute('dir')).toBe(false);
    });
  });
});
