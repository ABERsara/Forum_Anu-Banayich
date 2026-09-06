import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { NEVER, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { NewMessageComponent } from './new-message.component';
import type { UserPublic } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

function makeMember(overrides: Partial<UserPublic> = {}): UserPublic {
  return { id: 'member-1', first_name: 'שרה', last_name: 'לוי', ...overrides };
}

/**
 * A member whose name carries no Hebrew.
 *
 * A person's name is user-generated content — never translated (ABF-130).
 * Feeding a Latin name to the `HEBREW` sweeps below keeps them pointed at our
 * own copy, which is the thing they are meant to guard.
 */
function makeLatinMember(overrides: Partial<UserPublic> = {}): UserPublic {
  return makeMember({ first_name: 'Sarah', last_name: 'Levi', ...overrides });
}

describe('NewMessageComponent', () => {
  let fixture: ComponentFixture<NewMessageComponent>;
  let component: NewMessageComponent;
  let forumServiceMock: { getCellMembers: ReturnType<typeof vi.fn> };

  function setup(): void {
    TestBed.configureTestingModule({
      imports: [NewMessageComponent, translocoTesting()],
      providers: [provideRouter([]), { provide: ForumService, useValue: forumServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(NewMessageComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  it('loads cell members on init', () => {
    forumServiceMock = { getCellMembers: vi.fn().mockReturnValue(of([makeMember()])) };
    setup();

    expect(component.isLoading()).toBe(false);
    expect(component.hasError()).toBe(false);
    expect(component.members().length).toBe(1);
  });

  it('sets hasError when loading fails', () => {
    forumServiceMock = {
      getCellMembers: vi.fn().mockReturnValue(throwError(() => ({ status: 500 }))),
    };
    setup();

    expect(component.hasError()).toBe(true);
    expect(component.isLoading()).toBe(false);
  });

  it('shows the empty state when the cell has no other members', () => {
    forumServiceMock = { getCellMembers: vi.fn().mockReturnValue(of([])) };
    setup();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('אין חברים נוספים בתא שלך כרגע');
  });

  it('renders a link to each member', () => {
    forumServiceMock = {
      getCellMembers: vi.fn().mockReturnValue(of([makeMember({ id: 'member-2' })])),
    };
    setup();

    const link = (fixture.nativeElement as HTMLElement).querySelector('a.cell-members__item');
    expect(link?.getAttribute('href')).toBe('/messages/member-2');
    expect(link?.textContent).toContain('שרה');
  });

  function root(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return root().textContent ?? '';
  }

  function heading(): string {
    return root().querySelector('h1')!.textContent!.trim();
  }

  function switchToEnglish(): void {
    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();
  }

  /**
   * This screen was written against Transloco from the start (ABF-118), so
   * ABF-135 had no Hebrew here to replace — but it did rename this screen's
   * key group from `messages.newMessage` to `messages.new_message`, and a
   * rename that misses one call site shows up as a raw key on the page. These
   * assertions read the real `he.json` / `en.json`, so they fail on the miss.
   */
  describe('i18n', () => {
    it('reads in Hebrew exactly as it did before the keys were renamed', () => {
      forumServiceMock = { getCellMembers: vi.fn().mockReturnValue(of([makeMember()])) };
      setup();

      expect(heading()).toBe('חברי התא שלי');
    });

    it('leaves no Hebrew on the page in English', () => {
      forumServiceMock = { getCellMembers: vi.fn().mockReturnValue(of([makeLatinMember()])) };
      setup();

      switchToEnglish();

      expect(heading()).toBe('My cell members');
      expect(text()).toContain('Sarah Levi');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the empty state in English', () => {
      forumServiceMock = { getCellMembers: vi.fn().mockReturnValue(of([])) };
      setup();

      switchToEnglish();

      expect(text()).toContain('There are no other members in your cell yet.');
      expect(text()).not.toMatch(HEBREW);
    });

    it('leaves no Hebrew on the page while the list is still loading', () => {
      forumServiceMock = { getCellMembers: vi.fn().mockReturnValue(NEVER) };
      setup();
      expect(text()).toContain('טוען חברי תא...');

      switchToEnglish();

      expect(root().querySelector('app-loading-spinner')).toBeTruthy();
      expect(text()).toContain('Loading cell members...');
      expect(text()).not.toMatch(HEBREW);
    });

    /** Our own copy is a key, so a failure already on screen follows the switch. */
    it('re-renders the failure copy in the new language', () => {
      forumServiceMock = {
        getCellMembers: vi.fn().mockReturnValue(throwError(() => ({ status: 500 }))),
      };
      setup();
      expect(text()).toContain('אירעה שגיאה. נסו שוב.');

      switchToEnglish();

      expect(text()).toContain('Something went wrong. Please try again.');
      expect(text()).not.toMatch(HEBREW);
    });
  });
});
