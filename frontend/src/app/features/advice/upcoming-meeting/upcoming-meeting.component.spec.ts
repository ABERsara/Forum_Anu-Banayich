/**
 * One meeting in the professional's list, and what its creator can do to it
 * (ABF-163).
 *
 * Who may edit or cancel is the server's decision and is tested there. What
 * this screen owns is: drawing the two buttons for the creator and nobody
 * else, sending only what changed, never sending a cancellation she did not
 * confirm, and reporting a 403 upward so the consent step can come back.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { UpcomingMeetingComponent } from './upcoming-meeting.component';
import { GroupVisibility, SectorVisibility } from '../../../core/constants';
import type { Meeting } from '../../../core/models';
import { AuthService } from '../../../core/services/auth.service';
import { MeetingService } from '../../../core/services/meeting.service';
import { toLocalInputValue } from '../meeting-form';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

const HOUR = 60 * 60_000;

function makeMeeting(overrides: Partial<Meeting> = {}): Meeting {
  return {
    id: 'meeting-1',
    title: 'מפגש תמיכה',
    scheduled_at: '2030-05-01T11:30:00Z',
    duration_minutes: 60,
    meet_link: 'https://meet.google.com/abc-defg-hij',
    group_visibility: GroupVisibility.WIDOWS,
    sector_visibility: SectorVisibility.HASIDIC,
    creator: { id: 'pro-1', first_name: 'שרה', last_name: 'לוי' },
    created_at: '2026-10-05T09:00:00Z',
    ...overrides,
  };
}

describe('UpcomingMeetingComponent', () => {
  let fixture: ComponentFixture<UpcomingMeetingComponent>;
  let component: UpcomingMeetingComponent;
  let meetingServiceMock: {
    updateMeeting: ReturnType<typeof vi.fn>;
    cancelMeeting: ReturnType<typeof vi.fn>;
  };
  let updated: Meeting[];
  let cancelled: string[];
  let refusals: number;

  function setup(
    {
      meeting = makeMeeting(),
      viewerId = 'pro-1' as string | null,
    }: { meeting?: Meeting; viewerId?: string | null } = {},
    overrides: Partial<typeof meetingServiceMock> = {},
  ): void {
    meetingServiceMock = {
      updateMeeting: vi.fn().mockReturnValue(of(makeMeeting({ title: 'כותרת חדשה' }))),
      cancelMeeting: vi.fn().mockReturnValue(of(undefined)),
      ...overrides,
    };

    TestBed.configureTestingModule({
      imports: [UpcomingMeetingComponent, translocoTesting()],
      providers: [
        { provide: MeetingService, useValue: meetingServiceMock },
        {
          provide: AuthService,
          useValue: { currentUser: () => (viewerId ? { id: viewerId } : null) },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(UpcomingMeetingComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('meeting', meeting);
    updated = [];
    cancelled = [];
    refusals = 0;
    component.updated.subscribe((value) => updated.push(value));
    component.cancelled.subscribe((id) => cancelled.push(id));
    component.refused.subscribe(() => refusals++);
    fixture.detectChanges();
  }

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return element().textContent ?? '';
  }

  function editButton(): HTMLButtonElement | null {
    return element().querySelector<HTMLButtonElement>('.upcoming-meeting__btn--edit');
  }

  function cancelButton(): HTMLButtonElement | null {
    return element().querySelector<HTMLButtonElement>('.upcoming-meeting__btn--cancel');
  }

  function openEditor(): void {
    editButton()!.click();
    fixture.detectChanges();
  }

  describe('the row', () => {
    it('shows the meeting and the way in', () => {
      setup();

      expect(text()).toContain('מפגש תמיכה');
      expect(
        element().querySelector<HTMLAnchorElement>('.upcoming-meeting__join')?.getAttribute('href'),
      ).toBe('https://meet.google.com/abc-defg-hij');
    });

    it('offers its creator "ערכי" and "בטלי"', () => {
      setup();

      expect(editButton()?.textContent?.trim()).toBe('ערכי');
      expect(cancelButton()?.textContent?.trim()).toBe('בטלי');
    });

    /** A list of identical "Edit" buttons says nothing about which is which. */
    it('names the meeting in each button for a screen reader', () => {
      setup();

      expect(editButton()?.getAttribute('aria-label')).toBe('עריכת הפגישה מפגש תמיכה');
      expect(cancelButton()?.getAttribute('aria-label')).toBe('ביטול הפגישה מפגש תמיכה');
    });

    it('offers nobody else either button', () => {
      setup({ viewerId: 'someone-else' });

      expect(component.canManage()).toBe(false);
      expect(editButton()).toBeNull();
      expect(cancelButton()).toBeNull();
    });

    it('offers neither while nobody is signed in', () => {
      setup({ viewerId: null });

      expect(editButton()).toBeNull();
      expect(cancelButton()).toBeNull();
    });
  });

  describe('editing', () => {
    it('opens on the meeting as it stands, in the input’s own local shape', () => {
      setup();
      openEditor();

      expect(component.isEditing()).toBe(true);
      expect(component.form.controls.title.value).toBe('מפגש תמיכה');
      expect(component.form.controls.scheduled_at.value).toBe(
        toLocalInputValue(new Date('2030-05-01T11:30:00Z')),
      );
      expect(editButton()).toBeNull();
    });

    /** The button she pressed is gone, so focus must not be left on nothing. */
    it('moves focus into the title field', async () => {
      setup();
      openEditor();
      await fixture.whenStable();

      expect(document.activeElement).toBe(element().querySelector('input#edit-title-meeting-1'));
    });

    it('sends only a changed title', () => {
      setup();
      openEditor();
      component.form.patchValue({ title: 'כותרת חדשה' });

      component.save();

      expect(meetingServiceMock.updateMeeting).toHaveBeenCalledWith('meeting-1', {
        title: 'כותרת חדשה',
      });
    });

    it('sends only a changed time, as the zoned instant', () => {
      setup();
      openEditor();
      component.form.patchValue({ scheduled_at: '2030-06-02T18:00' });

      component.save();

      expect(meetingServiceMock.updateMeeting).toHaveBeenCalledWith('meeting-1', {
        scheduled_at: new Date('2030-06-02T18:00').toISOString(),
      });
    });

    it('closes and reports the saved meeting upward', () => {
      setup();
      openEditor();
      component.form.patchValue({ title: 'כותרת חדשה' });

      component.save();
      fixture.detectChanges();

      expect(component.isEditing()).toBe(false);
      expect(updated.map((meeting) => meeting.title)).toEqual(['כותרת חדשה']);
    });

    it('sends nothing when nothing changed, and just closes', () => {
      setup();
      openEditor();

      component.save();

      expect(meetingServiceMock.updateMeeting).not.toHaveBeenCalled();
      expect(component.isEditing()).toBe(false);
      expect(updated).toEqual([]);
    });

    it('sends nothing while the title is too short', () => {
      setup();
      openEditor();
      component.form.patchValue({ title: 'א' });

      component.save();
      fixture.detectChanges();

      expect(meetingServiceMock.updateMeeting).not.toHaveBeenCalled();
      expect(text()).toContain('יש להזין כותרת');
    });

    it('refuses a new time that has already passed', () => {
      setup();
      openEditor();
      component.form.patchValue({ scheduled_at: '2020-01-01T10:00' });

      component.save();

      expect(component.form.controls.scheduled_at.errors).toEqual({ pastDateTime: true });
      expect(meetingServiceMock.updateMeeting).not.toHaveBeenCalled();
    });

    /**
     * A meeting in progress started in the past. Its untouched start must
     * not block correcting the title — it is not sent, so it is not judged.
     */
    it('lets a meeting in progress have its title corrected', () => {
      const startedTenMinutesAgo = new Date(Date.now() - HOUR / 6).toISOString();
      setup({ meeting: makeMeeting({ scheduled_at: startedTenMinutesAgo }) });
      openEditor();
      component.form.patchValue({ title: 'כותרת מתוקנת' });

      component.save();

      expect(meetingServiceMock.updateMeeting).toHaveBeenCalledWith('meeting-1', {
        title: 'כותרת מתוקנת',
      });
    });

    it('closes without a request when she goes back without saving', () => {
      setup();
      openEditor();
      component.form.patchValue({ title: 'טיוטה' });

      element().querySelector<HTMLButtonElement>('.edit-form__discard')!.click();
      fixture.detectChanges();

      expect(component.isEditing()).toBe(false);
      expect(meetingServiceMock.updateMeeting).not.toHaveBeenCalled();
      expect(text()).toContain('מפגש תמיכה');
    });

    it('stays open with our own sentence when the save fails', () => {
      setup({}, { updateMeeting: vi.fn().mockReturnValue(throwError(() => ({ status: 500 }))) });
      openEditor();
      component.form.patchValue({ title: 'כותרת חדשה' });

      component.save();
      fixture.detectChanges();

      expect(component.isEditing()).toBe(true);
      expect(text()).toContain('עדכון הפגישה נכשל');
      expect(refusals).toBe(0);
    });

    it('shows the server’s sentence and reports a 403 upward', () => {
      setup(
        {},
        {
          updateMeeting: vi.fn().mockReturnValue(
            throwError(() => ({
              status: 403,
              error: { detail: 'ההרשאה ליומן Google פגה. יש לחבר את היומן מחדש.' },
            })),
          ),
        },
      );
      openEditor();
      component.form.patchValue({ title: 'כותרת חדשה' });

      component.save();
      fixture.detectChanges();

      expect(text()).toContain('ההרשאה ליומן Google פגה');
      expect(refusals).toBe(1);
    });
  });

  describe('cancelling', () => {
    it('asks first, and sends nothing until she confirms', () => {
      setup();

      cancelButton()!.click();
      fixture.detectChanges();

      expect(element().querySelector('app-confirm-dialog')).not.toBeNull();
      expect(text()).toContain('לבטל את הפגישה?');
      expect(meetingServiceMock.cancelMeeting).not.toHaveBeenCalled();
    });

    it('cancels on confirmation and reports which meeting', () => {
      setup();
      component.askToCancel();

      component.onCancelConfirmed();
      fixture.detectChanges();

      expect(meetingServiceMock.cancelMeeting).toHaveBeenCalledWith('meeting-1');
      expect(cancelled).toEqual(['meeting-1']);
      expect(element().querySelector('app-confirm-dialog')).toBeNull();
    });

    it('does nothing when she keeps the meeting', () => {
      setup();
      component.askToCancel();

      component.onCancelDismissed();
      fixture.detectChanges();

      expect(meetingServiceMock.cancelMeeting).not.toHaveBeenCalled();
      expect(element().querySelector('app-confirm-dialog')).toBeNull();
    });

    it('says so when the cancellation fails', () => {
      setup({}, { cancelMeeting: vi.fn().mockReturnValue(throwError(() => ({ status: 502 }))) });
      component.askToCancel();

      component.onCancelConfirmed();
      fixture.detectChanges();

      expect(cancelled).toEqual([]);
      expect(text()).toContain('ביטול הפגישה נכשל');
      expect(refusals).toBe(0);
    });

    it('reports a 403 upward', () => {
      setup({}, { cancelMeeting: vi.fn().mockReturnValue(throwError(() => ({ status: 403 }))) });
      component.askToCancel();

      component.onCancelConfirmed();

      expect(refusals).toBe(1);
    });

    it('holds both buttons while a cancellation is on its way', () => {
      setup();
      component.isCancelling.set(true);
      fixture.detectChanges();

      expect(editButton()?.disabled).toBe(true);
      expect(cancelButton()?.disabled).toBe(true);
    });
  });

  describe('language', () => {
    it('re-renders its own copy', () => {
      setup();

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      expect(editButton()?.textContent?.trim()).toBe('Edit');
      expect(cancelButton()?.textContent?.trim()).toBe('Cancel');
      // The title is hers, not ours: it stays in the language she wrote it in.
      expect(text().replace('מפגש תמיכה', '')).not.toMatch(HEBREW);
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      setup();

      expect(element().querySelector('.upcoming-meeting')?.hasAttribute('dir')).toBe(false);
    });
  });
});
