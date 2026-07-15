import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
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

  function setup(currentUser: UserProfile | null, isModerator = false, isAdmin = false): void {
    forumServiceMock = {
      getPost: vi.fn().mockReturnValue(of(makePost())),
      deletePost: vi.fn().mockReturnValue(of(makePost({ status: PostStatus.DELETED }))),
    };
    authServiceMock = {
      currentUser: vi.fn().mockReturnValue(currentUser),
      isModerator: vi.fn().mockReturnValue(isModerator),
      isAdmin: vi.fn().mockReturnValue(isAdmin),
    };
    navigateSpy = vi.fn();

    TestBed.configureTestingModule({
      imports: [ForumPostComponent],
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

      expect(component.errorMessage()).toBe('ההודעה לא נמצאה.');
    });

    it('shows a permission message on 403', () => {
      setup(makeUser());
      forumServiceMock.getPost.mockReturnValue(throwError(() => ({ status: 403 })));

      component.ngOnInit();

      expect(component.errorMessage()).toBe('אין לך הרשאה לצפות בהודעה זו.');
    });

    it('shows a generic message on other errors', () => {
      setup(makeUser());
      forumServiceMock.getPost.mockReturnValue(throwError(() => ({ status: 500 })));

      component.ngOnInit();

      expect(component.errorMessage()).toBe('אירעה שגיאה בטעינת ההודעה. נסה לרענן את הדף.');
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

      expect(component.deleteError()).toBe('אירעה שגיאה במחיקת ההודעה. נסה שוב.');
      expect(navigateSpy).not.toHaveBeenCalled();
    });
  });
});
