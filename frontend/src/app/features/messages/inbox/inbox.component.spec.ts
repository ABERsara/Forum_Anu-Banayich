import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { InboxComponent } from './inbox.component';
import type { UserPublic } from '../../../core/models';
import { ForumService } from '../../../core/services/forum.service';

function makeMember(overrides: Partial<UserPublic> = {}): UserPublic {
  return { id: 'member-1', first_name: 'שרה', last_name: 'לוי', ...overrides };
}

describe('InboxComponent', () => {
  let fixture: ComponentFixture<InboxComponent>;
  let component: InboxComponent;
  let forumServiceMock: { getCellMembers: ReturnType<typeof vi.fn> };

  function setup(): void {
    TestBed.configureTestingModule({
      imports: [InboxComponent],
      providers: [provideRouter([]), { provide: ForumService, useValue: forumServiceMock }],
    }).compileComponents();

    fixture = TestBed.createComponent(InboxComponent);
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
});
