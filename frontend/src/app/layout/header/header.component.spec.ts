import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { vi } from 'vitest';

import { HeaderComponent } from './header.component';
import { AuthService } from '../../core/services/auth.service';
import { LocaleService, type AppLang } from '../../core/services/locale.service';
import { HEBREW, translocoTesting } from '../../../testing/transloco-testing';

describe('HeaderComponent', () => {
  let fixture: ComponentFixture<HeaderComponent>;
  let langSignal: ReturnType<typeof signal<AppLang>>;
  let toggleLangSpy: ReturnType<typeof vi.fn>;

  /**
   * `translocoTesting()` replaces the HTTP loader ABF-126's version of this
   * spec provided: the header now renders text of its own, so the spec has to
   * assert against the real he/en files rather than an empty dictionary.
   */
  function setup(isLoggedIn: boolean, isUser = false): void {
    langSignal = signal<AppLang>('he');
    toggleLangSpy = vi.fn();

    TestBed.configureTestingModule({
      imports: [HeaderComponent, translocoTesting()],
      providers: [
        provideRouter([]),
        { provide: AuthService, useValue: { isLoggedIn: () => isLoggedIn, isUser: () => isUser } },
        { provide: LocaleService, useValue: { lang: langSignal, toggleLang: toggleLangSpy } },
      ],
    });

    fixture = TestBed.createComponent(HeaderComponent);
    fixture.detectChanges();
  }

  /**
   * The header's own text, with the language toggle cut out: that button names
   * Hebrew in Hebrew on purpose, so it is the one place a Hebrew word is meant
   * to survive into the English header.
   */
  function headerText(): string {
    const clone = (fixture.nativeElement as HTMLElement).cloneNode(true) as HTMLElement;
    clone.querySelector('.language-toggle')?.remove();
    return clone.textContent ?? '';
  }

  /** Switches both the translations and the mocked locale, as the real app does. */
  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    langSignal.set('en');
    fixture.detectChanges();
  }

  function logoText(): string {
    return fixture.nativeElement.querySelector('.header__logo').textContent.trim();
  }

  it('isHebrew() reflects LocaleService.lang()', () => {
    setup(false);

    expect(fixture.componentInstance.isHebrew()).toBe(true);

    langSignal.set('en');
    fixture.detectChanges();

    expect(fixture.componentInstance.isHebrew()).toBe(false);
  });

  it('clicking the language toggle calls LocaleService.toggleLang', () => {
    setup(false);

    const button = fixture.nativeElement.querySelector('.language-toggle') as HTMLButtonElement;
    button.click();

    expect(toggleLangSpy).toHaveBeenCalled();
  });

  describe('signed out', () => {
    it('shows the brand and the entry links in Hebrew', () => {
      setup(false);

      expect(logoText()).toBe('הפורום');
      expect(headerText()).toContain('כניסה');
      expect(headerText()).toContain('הרשמה');
    });

    it('shows them in English under an English locale', () => {
      setup(false);

      switchToEnglish();

      expect(logoText()).toBe('The Forum');
      expect(headerText()).toContain('Log in');
      expect(headerText()).toContain('Sign up');
      expect(headerText()).not.toMatch(HEBREW);
    });
  });

  describe('signed in', () => {
    function logoutText(): string {
      return fixture.nativeElement.querySelector('.header__logout').textContent.trim();
    }

    it('shows the home link and logout in Hebrew', () => {
      setup(true);

      expect(headerText()).toContain('בית');
      expect(logoutText()).toBe('התנתקות');
    });

    it('shows them in English under an English locale', () => {
      setup(true);

      switchToEnglish();

      expect(headerText()).toContain('Home');
      expect(logoutText()).toBe('Log out');
      expect(headerText()).not.toMatch(HEBREW);
    });

    /**
     * The messages link arrived from ABF-118 while this branch was rewriting
     * the nav around it, so it is the one label the merge had to move onto a
     * key by hand. These two pin both halves of that resolution: the link is
     * still role-gated as ABF-118 built it, and it is translated like the rest
     * of the nav rather than left as the Hebrew literal it came in as.
     */
    it('shows the messages link to a regular user, in both languages', () => {
      setup(true, true);

      expect(headerText()).toContain('הודעות');

      switchToEnglish();

      expect(headerText()).toContain('Messages');
      expect(headerText()).not.toMatch(HEBREW);
    });

    it('hides the messages link from a role that is not a plain user', () => {
      setup(true, false);

      expect(fixture.nativeElement.querySelector('.header__messages')).toBeNull();
    });
  });
});
