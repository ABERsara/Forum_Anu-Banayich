import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { NewMessageComponent } from './new-message.component';
import type { UserPublic } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';
import { translocoTesting } from '../../../../testing/transloco-testing';

function makeMember(overrides: Partial<UserPublic> = {}): UserPublic {
  return { id: 'member-1', first_name: 'שרה', last_name: 'לוי', ...overrides };
}

describe('NewMessageComponent', () => {
  let fixture: ComponentFixture<NewMessageComponent>;
  let component: NewMessageComponent;
  let forumServiceMock: {
    getCellMembers: ReturnType<typeof vi.fn>;
    searchUsers: ReturnType<typeof vi.fn>;
  };

  function setup(): void {
    TestBed.configureTestingModule({
      imports: [NewMessageComponent, translocoTesting()],
      providers: [provideRouter([]), { provide: ForumService, useValue: forumServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(NewMessageComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function typeQuery(value: string): void {
    component.searchControl.setValue(value);
    fixture.detectChanges();
  }

  beforeEach(() => {
    forumServiceMock = {
      getCellMembers: vi.fn().mockReturnValue(of([])),
      searchUsers: vi.fn().mockReturnValue(of([])),
    };
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads cell members on init', () => {
    forumServiceMock.getCellMembers.mockReturnValue(of([makeMember()]));
    setup();

    expect(component.isLoading()).toBe(false);
    expect(component.hasError()).toBe(false);
    expect(component.members().length).toBe(1);
  });

  it('sets hasError when loading fails', () => {
    forumServiceMock.getCellMembers.mockReturnValue(throwError(() => ({ status: 500 })));
    setup();

    expect(component.hasError()).toBe(true);
    expect(component.isLoading()).toBe(false);
  });

  it('shows the empty state when the cell has no other members', () => {
    setup();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('אין חברים נוספים בתא שלך כרגע');
  });

  it('renders a link to each member', () => {
    forumServiceMock.getCellMembers.mockReturnValue(of([makeMember({ id: 'member-2' })]));
    setup();

    const link = (fixture.nativeElement as HTMLElement).querySelector('a.cell-members__item');
    expect(link?.getAttribute('href')).toBe('/messages/member-2');
    expect(link?.textContent).toContain('שרה');
  });

  it('does not show the min-chars hint before the user has typed anything', () => {
    setup();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('#recipient-search-hint'),
    ).toBeNull();
  });

  it('shows the min-chars hint only while 1 char has been typed, and hides it again at 2+', () => {
    setup();

    typeQuery('א');
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('#recipient-search-hint'),
    ).toBeTruthy();

    typeQuery('אב');
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('#recipient-search-hint'),
    ).toBeNull();
  });

  it('does not call searchUsers for a query under 2 characters', async () => {
    vi.useFakeTimers();
    setup();

    typeQuery('א');
    await vi.advanceTimersByTimeAsync(300);

    expect(forumServiceMock.searchUsers).not.toHaveBeenCalled();
    expect(component.searchResults().length).toBe(0);
  });

  it('calls searchUsers after debounce once 2+ characters are typed and renders results', async () => {
    forumServiceMock.searchUsers.mockReturnValue(of([makeMember({ id: 'match-1' })]));
    vi.useFakeTimers();
    setup();

    typeQuery('שר');
    await vi.advanceTimersByTimeAsync(300);
    fixture.detectChanges();

    expect(forumServiceMock.searchUsers).toHaveBeenCalledWith('שר');
    const link = (fixture.nativeElement as HTMLElement).querySelector(
      '.cell-search a.cell-members__item',
    );
    expect(link?.getAttribute('href')).toBe('/messages/match-1');
  });

  it('hides the full member list while a search is active, to avoid showing a match twice', async () => {
    const match = makeMember({ id: 'match-1' });
    forumServiceMock.getCellMembers.mockReturnValue(of([match]));
    forumServiceMock.searchUsers.mockReturnValue(of([match]));
    vi.useFakeTimers();
    setup();
    expect(
      (fixture.nativeElement as HTMLElement).querySelectorAll('a.cell-members__item').length,
    ).toBe(1);

    typeQuery('שר');
    await vi.advanceTimersByTimeAsync(300);
    fixture.detectChanges();

    const links = (fixture.nativeElement as HTMLElement).querySelectorAll('a.cell-members__item');
    expect(links.length).toBe(1);
    expect(links[0].closest('.cell-search')).toBeTruthy();
  });

  it('shows the no-results state after a real search returns nothing', async () => {
    forumServiceMock.searchUsers.mockReturnValue(of([]));
    vi.useFakeTimers();
    setup();

    typeQuery('שר');
    await vi.advanceTimersByTimeAsync(300);
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('לא נמצאו חברים תואמים בתא שלך');
  });

  it('shows an error state when searchUsers fails', async () => {
    forumServiceMock.searchUsers.mockReturnValue(throwError(() => ({ status: 500 })));
    vi.useFakeTimers();
    setup();

    typeQuery('שר');
    await vi.advanceTimersByTimeAsync(300);
    fixture.detectChanges();

    expect(component.searchError()).toBe(true);
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('.cell-search .error-display'),
    ).toBeTruthy();
  });

  it('resets results when the query is cleared back below 2 characters', async () => {
    forumServiceMock.searchUsers.mockReturnValue(of([makeMember({ id: 'match-1' })]));
    vi.useFakeTimers();
    setup();

    typeQuery('שר');
    await vi.advanceTimersByTimeAsync(300);
    fixture.detectChanges();
    expect(component.searchResults().length).toBe(1);

    typeQuery('');
    await vi.advanceTimersByTimeAsync(300);
    fixture.detectChanges();

    expect(component.searchResults().length).toBe(0);
    expect(component.hasSearched()).toBe(false);
  });
});
