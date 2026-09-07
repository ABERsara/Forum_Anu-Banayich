/**
 * The profile screen had no spec before ABF-136.
 *
 * It is a heading and five label/value rows, and nothing else — which is
 * exactly the shape that needs a guard once the copy becomes keys: without one,
 * nothing catches a label falling back to hardcoded Hebrew, a raw
 * `profile.status_label` reaching the page, or the inline `direction: rtl`
 * coming back and pinning an English page to RTL.
 *
 * Three of the five rows render the shared maps from `core/constants`, which
 * ABF-127 already moved to keys. This ticket adds no copy of its own for them,
 * so the last test here is what says the rows still read the shared map.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';

import { ProfileComponent } from './profile.component';
import { AccountStatus, Sector, UserRole, UserType } from '../../core/constants';
import { UserProfile } from '../../core/models';
import { AuthService } from '../../core/services/auth.service';
import { HEBREW, translocoTesting } from '../../../testing/transloco-testing';

/** A member as the API returns them, with every optional field filled in. */
function makeUser(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    id: 'u1',
    first_name: 'שרה',
    last_name: 'לוי',
    email: 'sara@example.com',
    role: UserRole.USER,
    user_type: UserType.WIDOW,
    sector: Sector.SEPHARDIC,
    birth_date: null,
    account_status: AccountStatus.ACTIVE,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

/**
 * The same member with a Latin name, for the sweep below.
 *
 * `not.toMatch(HEBREW)` cannot tell our own copy from the name a member typed,
 * and a member's name is theirs in either language (CONTRIBUTING §6, ABF-130) —
 * so the sweep runs against a fixture that has no Hebrew of its own to trip on.
 */
function makeLatinUser(): UserProfile {
  return makeUser({ first_name: 'Sarah', last_name: 'Levi' });
}

describe('ProfileComponent', () => {
  let fixture: ComponentFixture<ProfileComponent>;

  function renderFor(user: UserProfile | null): void {
    TestBed.resetTestingModule();

    TestBed.configureTestingModule({
      imports: [ProfileComponent, translocoTesting()],
      providers: [
        { provide: AuthService, useValue: { currentUser: signal<UserProfile | null>(user) } },
      ],
    });

    fixture = TestBed.createComponent(ProfileComponent);
    fixture.detectChanges();
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function heading(): string {
    return fixture.nativeElement.querySelector('h1').textContent.trim();
  }

  /** The five rows, whitespace normalised the way a reader sees them. */
  function rows(): string[] {
    return [...(fixture.nativeElement as HTMLElement).querySelectorAll('p')].map((row) =>
      (row.textContent ?? '').replace(/\s+/g, ' ').trim(),
    );
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  it('shows the signed-in member their own details', () => {
    renderFor(makeUser());

    expect(rows()).toEqual([
      'שם: שרה לוי',
      'מייל: sara@example.com',
      'קבוצה: אלמנה',
      'מגזר: ספרדי',
      'סטטוס: פעיל',
    ]);
  });

  it('shows the heading alone until the profile has loaded', () => {
    renderFor(null);

    expect(heading()).toBe('הפרופיל שלי');
    expect(rows()).toEqual([]);
  });

  /** `user_type` and `sector` are nullable — the row stays empty, not "null". */
  it('leaves the group and sector rows blank for a member who has neither', () => {
    renderFor(makeUser({ user_type: null, sector: null }));

    expect(rows()[2]).toBe('קבוצה:');
    expect(rows()[3]).toBe('מגזר:');
    expect(text()).not.toContain('null');
    expect(text()).not.toContain('undefined');
  });

  describe('i18n', () => {
    it('reads in Hebrew exactly as it did before the keys went in', () => {
      renderFor(makeUser());

      expect(heading()).toBe('הפרופיל שלי');
      expect(rows()).toEqual([
        'שם: שרה לוי',
        'מייל: sara@example.com',
        'קבוצה: אלמנה',
        'מגזר: ספרדי',
        'סטטוס: פעיל',
      ]);
    });

    it('leaves no Hebrew on the page in English', () => {
      renderFor(makeLatinUser());

      switchToEnglish();

      expect(heading()).toBe('My profile');
      expect(rows()).toEqual([
        'Name: Sarah Levi',
        'Email: sara@example.com',
        'Group: Widow',
        'Sector: Sephardic',
        'Status: Active',
      ]);
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the page in English before the profile has loaded', () => {
      renderFor(null);

      switchToEnglish();

      expect(heading()).toBe('My profile');
      expect(text()).not.toMatch(HEBREW);
    });

    /** A member's name is theirs, not UI copy — it survives the switch as typed. */
    it("keeps the member's own name and address in the language they wrote them", () => {
      renderFor(makeUser());

      switchToEnglish();

      expect(rows()[0]).toBe('Name: שרה לוי');
      expect(rows()[1]).toBe('Email: sara@example.com');
    });

    /**
     * The three enum rows render the shared maps from `core/constants`, so this
     * ticket adds no `profile.*` copy of "אלמנה" — the duplication ABF-127
     * removed. Re-pointing the shared key is what a private copy would not
     * follow.
     */
    it('reads the group, sector and status off the shared label maps', () => {
      renderFor(makeUser());
      const transloco = TestBed.inject(TranslocoService);

      transloco.setTranslationKey('constants.user_type.widow', 'תווית אחרת', { lang: 'he' });
      fixture.detectChanges();

      expect(rows()[2]).toBe('קבוצה: תווית אחרת');
      expect(rows()[3]).toBe(`מגזר: ${transloco.translate('constants.sector.sephardic')}`);
      expect(rows()[4]).toBe(`סטטוס: ${transloco.translate('constants.account_status.active')}`);
    });

    /**
     * The page took its direction from an inline `direction: rtl` before this
     * ticket, which no language switch could undo. It follows `<html dir>` now —
     * the padding beside it was never directional and stays (ABF-134).
     */
    it('does not pin its own text direction — it follows <html dir>', () => {
      renderFor(makeUser());
      const host = fixture.nativeElement as HTMLElement;
      const page = host.querySelector('div') as HTMLElement;

      expect(host.hasAttribute('dir')).toBe(false);
      expect(page.hasAttribute('dir')).toBe(false);
      expect(page.style.direction).toBe('');
      expect(page.style.padding).toBe('1rem');
    });
  });
});
