import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { Subject, of, throwError } from 'rxjs';
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

  /** `loadFailure`, when given, is thrown by `getPost` instead of the post. */
  async function setup(
    currentUser: UserProfile | null = makeUser(),
    post: ForumPost = makePost(),
    loadFailure?: unknown,
  ): Promise<void> {
    forumServiceMock = {
      getPost: vi.fn().mockReturnValue(loadFailure ? throwError(() => loadFailure) : of(post)),
      updatePost: vi.fn().mockReturnValue(of(makePost({ title: 'כותרת מעודכנת' }))),
    };

    await TestBed.configureTestingModule({
      imports: [EditPostComponent, translocoTesting()],
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

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
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
      await setup(makeUser(), makePost(), { status: 404 });

      expect(component.loadErrorKey()).toBe('forum.errors.not_found');
      expect(text()).toContain('ההודעה לא נמצאה.');
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
      fixture.detectChanges();

      expect(component.saveErrorKey()).toBe('forum.errors.edit_forbidden');
      expect(text()).toContain('אין לך הרשאה לערוך הודעה זו.');
      expect(component.isSaving()).toBe(false);
    });
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as it did before the keys went in', async () => {
      await setup();

      expect(fixture.nativeElement.querySelector('.edit-post-title').textContent.trim()).toBe(
        'עריכת הודעה',
      );
      expect(text()).toContain('חזרה לפורום');
      expect(text()).toContain('כותרת');
      expect(text()).toContain('תוכן');
      expect(text()).toContain('שמירה');
    });

    it('leaves no Hebrew on the page in English', async () => {
      await setup();

      switchToEnglish();

      expect(fixture.nativeElement.querySelector('.edit-post-title').textContent.trim()).toBe(
        'Edit post',
      );
      expect(text()).toContain('Back to the forum');
      expect(text()).toContain('Title');
      expect(text()).toContain('Content');
      expect(text()).toContain('Save');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the validation messages too', async () => {
      await setup();
      component.form.setValue({ title: '', content: '' });

      component.onSubmit();
      switchToEnglish();

      expect(text()).toContain('Please enter a title (2 to 256 characters)');
      expect(text()).toContain('Please enter content (up to 5000 characters)');
      expect(text()).not.toMatch(HEBREW);
    });

    it('captions the spinner in English', async () => {
      await setup();
      forumServiceMock.updatePost.mockReturnValue(new Subject());
      component.form.setValue({ title: 'An updated title', content: 'Body text' });

      component.onSubmit();
      switchToEnglish();

      expect(text()).toContain('Saving...');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the "not your post" notice', async () => {
      await setup(makeUser({ id: 'someone-else' }));
      expect(text()).toContain('אין לך הרשאה לערוך הודעה זו.');

      switchToEnglish();

      expect(text()).toContain('You do not have permission to edit this post.');
      expect(text()).not.toMatch(HEBREW);
    });

    /** The failure is held as a key, so it follows the switch instead of freezing. */
    it('re-renders a load failure that is already on screen', async () => {
      await setup(makeUser(), makePost(), { status: 500 });
      expect(text()).toContain('אירעה שגיאה. נסה שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong. Please try again.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await setup();

      expect(fixture.nativeElement.querySelector('.edit-post-page').hasAttribute('dir')).toBe(
        false,
      );
    });
  });
});
