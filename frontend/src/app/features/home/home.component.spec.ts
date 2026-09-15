import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';

import { HomeComponent } from './home.component';
import { AccountStatus, UserRole } from '../../core/constants';
import { UserProfile } from '../../core/models';
import { AuthService } from '../../core/services/auth.service';
import { HEBREW, translocoTesting } from '../../../testing/transloco-testing';

const USER: UserProfile = {
  id: 'u1',
  first_name: 'שרה',
  last_name: 'לוי',
  email: 'sara@example.com',
  role: UserRole.USER,
  user_type: null,
  sector: null,
  birth_date: null,
  account_status: AccountStatus.ACTIVE,
  created_at: '2026-01-01T00:00:00Z',
};

describe('HomeComponent', () => {
  let fixture: ComponentFixture<HomeComponent>;
  let currentUser: ReturnType<typeof signal<UserProfile | null>>;

  function setup(role: UserRole | null): void {
    currentUser = signal<UserProfile | null>(role === null ? null : { ...USER, role });

    TestBed.configureTestingModule({
      imports: [HomeComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        {
          provide: AuthService,
          useValue: {
            currentUser,
            isUser: () => role === UserRole.USER,
            isAdmin: () => role === UserRole.ADMIN,
            isModerator: () => role === UserRole.MODERATOR,
            isProfessional: () => role === UserRole.PROFESSIONAL,
          },
        },
      ],
    });

    fixture = TestBed.createComponent(HomeComponent);
    fixture.detectChanges();
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  /**
   * The page's copy, with the greeting cut out: it carries the member's own
   * name, which is their data and stays as they typed it in either language.
   */
  function copyOnly(): string {
    const clone = (fixture.nativeElement as HTMLElement).cloneNode(true) as HTMLElement;
    clone.querySelector('.home__subtitle')?.remove();
    return clone.textContent ?? '';
  }

  /** The home card that opens the AI agent catalog, if this role has one. */
  function agentsLink(): HTMLAnchorElement | null {
    return (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>(
      'a[href="/agents"]',
    );
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  describe('a member', () => {
    it('is welcomed by name in Hebrew', () => {
      setup(UserRole.USER);

      expect(fixture.nativeElement.querySelector('.home__title').textContent.trim()).toBe(
        'ברוכים הבאים',
      );
      expect(fixture.nativeElement.querySelector('.home__subtitle').textContent.trim()).toBe(
        'שלום, שרה לוי',
      );
    });

    it('sees the forum and advice cards in Hebrew', () => {
      setup(UserRole.USER);

      expect(text()).toContain('פורום');
      expect(text()).toContain('שאלות ותשובות מהקהילה');
      expect(text()).toContain('ייעוץ');
      expect(text()).toContain('קבלת ייעוץ אישי ומקצועי בנושאים שמעסיקים אתכם.');
    });

    /**
     * The cards on this page are the only way into a feature — `header.component`
     * carries no navigation links — so the agent catalog is unreachable without
     * this one. ABF-123's acceptance criterion is exactly that.
     */
    it('sees the AI agents card, and it leads to the catalog', () => {
      setup(UserRole.USER);

      const link = agentsLink();
      expect(link).toBeTruthy();
      expect(link!.getAttribute('href')).toBe('/agents');
      expect(link!.textContent).toContain('סוכני AI');
      expect(link!.textContent).toContain('מידע כללי, מיד');
      expect(link!.textContent).toContain('שאלה לסוכן AI על זכויות ונהלים');
    });

    it('sees the same AI agents card in English', () => {
      setup(UserRole.USER);

      switchToEnglish();

      const link = agentsLink()!;
      expect(link.textContent).toContain('AI agents');
      expect(link.textContent).toContain('General information, right away');
      expect(link.textContent).not.toMatch(HEBREW);
    });

    /** The card belongs to members. No other role is offered an agent. */
    it.each([UserRole.ADMIN, UserRole.MODERATOR, UserRole.PROFESSIONAL])(
      'does not show it to a %s',
      (role) => {
        setup(role);

        expect(agentsLink()).toBeNull();
      },
    );

    /**
     * The greeting is the one interpolated string on this page: the name is a
     * parameter, so it has to stay put while the sentence around it changes.
     */
    it('sees the same page in English, name intact', () => {
      setup(UserRole.USER);

      switchToEnglish();

      expect(fixture.nativeElement.querySelector('.home__title').textContent.trim()).toBe(
        'Welcome',
      );
      expect(fixture.nativeElement.querySelector('.home__subtitle').textContent.trim()).toBe(
        'Hello, שרה לוי',
      );
      expect(text()).toContain('Forum');
      expect(text()).toContain('Questions and answers from the community');
      expect(text()).toContain('Advice');
    });
  });

  describe('the other roles', () => {
    it.each([
      [UserRole.ADMIN, 'ניהול', 'Administration'],
      [UserRole.MODERATOR, 'מבקר', 'Moderator'],
      [UserRole.PROFESSIONAL, 'ייעוץ מקצועי', 'Professional advice'],
    ])('shows the %s card in both languages', (role, hebrew, english) => {
      setup(role);
      expect(text()).toContain(hebrew);

      switchToEnglish();

      expect(text()).toContain(english);
      expect(copyOnly()).not.toMatch(HEBREW);
    });
  });

  describe('before the profile arrives', () => {
    it('shows the spinner caption in Hebrew, then in English', () => {
      setup(null);

      expect(text()).toContain('טוען...');

      switchToEnglish();

      expect(text()).toContain('Loading...');
      expect(copyOnly()).not.toMatch(HEBREW);
    });
  });

  it('does not pin its own text direction — it follows <html dir>', () => {
    setup(UserRole.USER);

    expect(fixture.nativeElement.querySelector('.home').hasAttribute('dir')).toBe(false);
  });
});
