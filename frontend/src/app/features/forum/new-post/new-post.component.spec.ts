import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { NewPostComponent } from './new-post.component';
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

const CREATED_POST: ForumPost = {
  id: 'post-1',
  title: 'כותרת',
  content: 'תוכן',
  group_visibility: GroupVisibility.WIDOWS,
  sector_visibility: SectorVisibility.HASIDIC,
  status: PostStatus.VISIBLE,
  report_count: 0,
  author: { id: 'author-1', first_name: 'שרה', last_name: 'לוי' },
  attachment_url: null,
  created_at: '2026-07-16T10:00:00',
  updated_at: '2026-07-16T10:00:00',
};

describe('NewPostComponent', () => {
  let fixture: ComponentFixture<NewPostComponent>;
  let component: NewPostComponent;
  let forumServiceMock: { createPost: ReturnType<typeof vi.fn> };
  let router: Router;

  async function setup(currentUser: UserProfile | null = makeUser()): Promise<void> {
    forumServiceMock = { createPost: vi.fn().mockReturnValue(of(CREATED_POST)) };

    await TestBed.configureTestingModule({
      imports: [NewPostComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        { provide: ForumService, useValue: forumServiceMock },
        { provide: AuthService, useValue: { currentUser: () => currentUser } },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);

    fixture = TestBed.createComponent(NewPostComponent);
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

  /** Fills the form with values that carry no Hebrew of their own. */
  function fillValidForm(): void {
    component.form.patchValue({
      title: 'A new post',
      content: 'Body text',
      group_visibility: GroupVisibility.WIDOWS,
      sector_visibility: SectorVisibility.HASIDIC,
    });
  }

  it('restricts group/sector options to the user’s own scope plus "all"', async () => {
    await setup(makeUser({ user_type: UserType.WIDOW, sector: Sector.HASIDIC }));

    expect(component.groupOptions()).toEqual([GroupVisibility.WIDOWS, GroupVisibility.ALL]);
    expect(component.sectorOptions()).toEqual([SectorVisibility.HASIDIC, SectorVisibility.ALL]);
  });

  it('defaults the form to the user’s own group/sector, not "all"', async () => {
    await setup(makeUser({ user_type: UserType.WIDOW, sector: Sector.HASIDIC }));

    expect(component.form.value.group_visibility).toBe(GroupVisibility.WIDOWS);
    expect(component.form.value.sector_visibility).toBe(SectorVisibility.HASIDIC);
  });

  it('does not submit an invalid form', async () => {
    await setup();

    component.onSubmit();

    expect(forumServiceMock.createPost).not.toHaveBeenCalled();
  });

  it('creates the post and navigates to it on success', async () => {
    await setup();
    component.form.patchValue({
      title: 'כותרת חדשה',
      content: 'תוכן ההודעה',
      group_visibility: GroupVisibility.WIDOWS,
      sector_visibility: SectorVisibility.HASIDIC,
    });

    component.onSubmit();

    expect(forumServiceMock.createPost).toHaveBeenCalledWith({
      title: 'כותרת חדשה',
      content: 'תוכן ההודעה',
      group_visibility: GroupVisibility.WIDOWS,
      sector_visibility: SectorVisibility.HASIDIC,
    });
    expect(router.navigate).toHaveBeenCalledWith(['/forum', 'post-1']);
  });

  it('captures a selected attachment in the form but never sends it to the backend', async () => {
    await setup();
    component.form.patchValue({
      title: 'כותרת חדשה',
      content: 'תוכן ההודעה',
      group_visibility: GroupVisibility.WIDOWS,
      sector_visibility: SectorVisibility.HASIDIC,
    });
    const file = new File(['data'], 'attachment.pdf', { type: 'application/pdf' });

    component.onFileSelected(file);
    expect(component.form.controls.attachment.value).toBe(file);

    component.onSubmit();

    expect(forumServiceMock.createPost).toHaveBeenCalledWith(
      expect.not.objectContaining({ attachment: expect.anything() }),
    );
  });

  it('shows the backend error detail and stops loading when submission fails', async () => {
    await setup();
    forumServiceMock.createPost.mockReturnValue(
      throwError(() => ({ error: { detail: 'שגיאה מהשרת' } })),
    );
    component.form.patchValue({
      title: 'כותרת חדשה',
      content: 'תוכן ההודעה',
      group_visibility: GroupVisibility.WIDOWS,
      sector_visibility: SectorVisibility.HASIDIC,
    });

    component.onSubmit();
    fixture.detectChanges();

    expect(component.error()).toEqual({ key: '', text: 'שגיאה מהשרת' });
    expect(text()).toContain('שגיאה מהשרת');
    expect(component.isLoading()).toBe(false);
  });

  /** The other branch of the same split: no `detail`, so our own copy stands in. */
  it('falls back to our own copy when the request fails without a detail', async () => {
    await setup();
    forumServiceMock.createPost.mockReturnValue(throwError(() => ({ status: 0 })));
    fillValidForm();

    component.onSubmit();
    fixture.detectChanges();

    expect(component.error()).toEqual({ key: 'forum.errors.create_failed', text: '' });
    expect(text()).toContain('אירעה שגיאה בפרסום ההודעה.');
    expect(component.isLoading()).toBe(false);
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as it did before the keys went in', async () => {
      await setup();

      expect(fixture.nativeElement.querySelector('.new-post-title').textContent.trim()).toBe(
        'פרסום הודעה חדשה',
      );
      expect(text()).toContain('חזרה לפורום');
      expect(text()).toContain('כותרת');
      expect(text()).toContain('תוכן');
      expect(text()).toContain('קהל יעד – קבוצה');
      expect(text()).toContain('קהל יעד – מגזר');
      expect(text()).toContain('צירוף קובץ (אופציונלי)');
      expect(text()).toContain('פרסם');
    });

    it('leaves no Hebrew on the page in English, audience labels included', async () => {
      await setup();

      switchToEnglish();

      expect(fixture.nativeElement.querySelector('.new-post-title').textContent.trim()).toBe(
        'New post',
      );
      expect(text()).toContain('Back to the forum');
      expect(text()).toContain('Title');
      expect(text()).toContain('Content');
      expect(text()).toContain('Audience – group');
      expect(text()).toContain('Audience – sector');
      // The option values come from core/constants (ABF-127), not from forum.*
      expect(text()).toContain('Widows');
      expect(text()).toContain('Everyone');
      expect(text()).toContain('Hasidic');
      expect(text()).toContain('All sectors');
      expect(text()).toContain('Attach a file (optional)');
      expect(text()).toContain('Publish');
      expect(text()).not.toMatch(HEBREW);
    });

    it('translates the validation messages too', async () => {
      await setup();

      component.onSubmit();
      switchToEnglish();

      expect(text()).toContain('Please enter a title (2 to 256 characters)');
      expect(text()).toContain('Please enter content (up to 5000 characters)');
      expect(text()).not.toMatch(HEBREW);
    });

    it('captions the spinner in English', async () => {
      await setup();
      forumServiceMock.createPost.mockReturnValue(new Subject());
      fillValidForm();

      component.onSubmit();
      switchToEnglish();

      expect(text()).toContain('Publishing...');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is held as a key, so it follows the switch instead of freezing. */
    it('re-renders our own failure copy when the language changes', async () => {
      await setup();
      forumServiceMock.createPost.mockReturnValue(throwError(() => ({ status: 0 })));
      fillValidForm();
      component.onSubmit();
      fixture.detectChanges();
      expect(text()).toContain('אירעה שגיאה בפרסום ההודעה.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong publishing the post.');
      expect(text()).not.toMatch(HEBREW);
    });

    /**
     * The other half of the split: the API wrote that sentence, so it is shown
     * as it arrived. It does not follow the UI language — only the backend can
     * change that (CONTRIBUTING §6).
     */
    it('leaves a sentence the API wrote exactly as it arrived', async () => {
      await setup();
      forumServiceMock.createPost.mockReturnValue(
        throwError(() => ({ error: { detail: 'שגיאה מהשרת' } })),
      );
      fillValidForm();
      component.onSubmit();
      fixture.detectChanges();

      switchToEnglish();

      expect(text()).toContain('שגיאה מהשרת');
    });

    /**
     * `app-file-upload` resolves its own size complaint and emits it as text,
     * so this one is shown without the pipe — a key would have leaked instead.
     */
    it('shows the upload complaint as the shared component resolved it', async () => {
      await setup();

      component.onFileError('הקובץ גדול מדי. הגודל המקסימלי הוא 5 MB');
      fixture.detectChanges();

      expect(text()).toContain('הקובץ גדול מדי. הגודל המקסימלי הוא 5 MB');
    });

    it('does not pin its own text direction — it follows <html dir>', async () => {
      await setup();

      expect(fixture.nativeElement.querySelector('.new-post-page').hasAttribute('dir')).toBe(false);
    });
  });
});
