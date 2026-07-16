import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
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
      imports: [NewPostComponent],
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

  it('restricts group/sector options to the user’s own scope plus "all"', async () => {
    await setup(makeUser({ user_type: UserType.WIDOW, sector: Sector.HASIDIC }));

    expect(component.groupOptions()).toEqual([GroupVisibility.WIDOWS, GroupVisibility.ALL]);
    expect(component.sectorOptions()).toEqual([SectorVisibility.HASIDIC, SectorVisibility.ALL]);
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

    expect(component.errorMessage()).toBe('שגיאה מהשרת');
    expect(component.isLoading()).toBe(false);
  });
});
