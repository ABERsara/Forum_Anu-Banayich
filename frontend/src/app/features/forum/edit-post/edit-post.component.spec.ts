import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { EditPostComponent } from './edit-post.component';
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

describe('EditPostComponent', () => {
  let fixture: ComponentFixture<EditPostComponent>;
  let component: EditPostComponent;
  let forumServiceMock: { getPost: ReturnType<typeof vi.fn>; updatePost: ReturnType<typeof vi.fn> };
  let router: Router;

  async function setup(currentUser: UserProfile | null = makeUser()): Promise<void> {
    forumServiceMock = {
      getPost: vi.fn().mockReturnValue(of(makePost())),
      updatePost: vi.fn().mockReturnValue(of(makePost({ title: 'כותרת מעודכנת' }))),
    };

    await TestBed.configureTestingModule({
      imports: [EditPostComponent],
      providers: [
        provideRouter([]),
        { provide: ForumService, useValue: forumServiceMock },
        { provide: AuthService, useValue: { currentUser: () => currentUser } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ id: 'post-1' }) } },
        },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);

    fixture = TestBed.createComponent(EditPostComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  describe('loading the post', () => {
    it('loads the post and pre-fills the form', async () => {
      await setup();

      expect(forumServiceMock.getPost).toHaveBeenCalledWith('post-1');
      expect(component.form.getRawValue()).toEqual({
        title: 'כותרת',
        content: 'תוכן ההודעה',
      });
    });

    it('shows a not-found message on 404', async () => {
      forumServiceMock = {
        getPost: vi.fn().mockReturnValue(throwError(() => ({ status: 404 }))),
        updatePost: vi.fn(),
      };
      await TestBed.configureTestingModule({
        imports: [EditPostComponent],
        providers: [
          provideRouter([]),
          { provide: ForumService, useValue: forumServiceMock },
          { provide: AuthService, useValue: { currentUser: () => makeUser() } },
          {
            provide: ActivatedRoute,
            useValue: { snapshot: { paramMap: convertToParamMap({ id: 'post-1' }) } },
          },
        ],
      }).compileComponents();
      fixture = TestBed.createComponent(EditPostComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();

      expect(component.loadError()).toBe('ההודעה לא נמצאה.');
    });
  });

  describe('isAuthor', () => {
    it('is true for the post author', async () => {
      await setup(makeUser({ id: 'author-1' }));

      expect(component.isAuthor()).toBe(true);
    });

    it('is false for a different user', async () => {
      await setup(makeUser({ id: 'someone-else' }));

      expect(component.isAuthor()).toBe(false);
    });
  });

  describe('submit flow', () => {
    it('does not submit an invalid form', async () => {
      await setup();
      component.form.setValue({ title: '', content: '' });

      component.onSubmit();

      expect(forumServiceMock.updatePost).not.toHaveBeenCalled();
    });

    it('updates the post and navigates back to it on success', async () => {
      await setup();
      component.form.setValue({ title: 'כותרת מעודכנת', content: 'תוכן ההודעה' });

      component.onSubmit();

      expect(forumServiceMock.updatePost).toHaveBeenCalledWith('post-1', {
        title: 'כותרת מעודכנת',
        content: 'תוכן ההודעה',
      });
      expect(router.navigate).toHaveBeenCalledWith(['/forum', 'post-1']);
    });

    it('shows an error and stops loading when the save fails', async () => {
      await setup();
      forumServiceMock.updatePost.mockReturnValue(throwError(() => ({ status: 403 })));
      component.form.setValue({ title: 'כותרת מעודכנת', content: 'תוכן ההודעה' });

      component.onSubmit();

      expect(component.saveError()).toBe('אין לך הרשאה לערוך הודעה זו.');
      expect(component.isSaving()).toBe(false);
    });
  });
});
