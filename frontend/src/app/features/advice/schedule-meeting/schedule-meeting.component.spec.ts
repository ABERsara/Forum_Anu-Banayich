/**
 * The scheduling screen.
 *
 * What matters here is the consent dance and the shape of what gets sent.
 * Whether a professional may convene a given cell is the server's decision and
 * is tested there; this screen only has to ask for her consent status before
 * letting her submit, send a timestamp that states its zone, and ask again
 * after a 403 — because the two kinds of 403 come back as finished sentences
 * and cannot be told apart from the body.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ScheduleMeetingComponent } from './schedule-meeting.component';
import { GroupVisibility, SectorVisibility } from '../../../core/constants';
import type { CalendarStatus, Meeting } from '../../../core/models';
import { MeetingService } from '../../../core/services/meeting.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

const AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth?client_id=x&state=signed';

const CONNECTED: CalendarStatus = {
  connected: true,
  connected_at: '2026-10-05T09:00:00Z',
  authorization_url: AUTH_URL,
};

const NOT_CONNECTED: CalendarStatus = {
  connected: false,
  connected_at: null,
  authorization_url: AUTH_URL,
};

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

describe('ScheduleMeetingComponent', () => {
  let fixture: ComponentFixture<ScheduleMeetingComponent>;
  let component: ScheduleMeetingComponent;
  let meetingServiceMock: {
    getCalendarStatus: ReturnType<typeof vi.fn>;
    getUpcomingMeetings: ReturnType<typeof vi.fn>;
    createMeeting: ReturnType<typeof vi.fn>;
  };

  function setup(overrides: Partial<typeof meetingServiceMock> = {}): void {
    meetingServiceMock = {
      getCalendarStatus: vi.fn().mockReturnValue(of(CONNECTED)),
      getUpcomingMeetings: vi.fn().mockReturnValue(of([])),
      createMeeting: vi.fn().mockReturnValue(of(makeMeeting())),
      ...overrides,
    };

    TestBed.configureTestingModule({
      imports: [ScheduleMeetingComponent, translocoTesting()],
      providers: [{ provide: MeetingService, useValue: meetingServiceMock }, provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(ScheduleMeetingComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return element().textContent ?? '';
  }

  function submitButton(): HTMLButtonElement {
    return element().querySelector<HTMLButtonElement>('.meeting-form__submit')!;
  }

  /** A form filled the way a professional would fill it. */
  function fillForm(scheduledAt = '2030-05-01T14:30'): void {
    component.form.patchValue({
      title: 'מפגש תמיכה',
      scheduled_at: scheduledAt,
      group_visibility: GroupVisibility.WIDOWS,
      sector_visibility: SectorVisibility.HASIDIC,
    });
    fixture.detectChanges();
  }

  describe('on the way in', () => {
    it('asks whether the calendar is linked, and what is already scheduled', () => {
      setup();

      expect(meetingServiceMock.getCalendarStatus).toHaveBeenCalledOnce();
      expect(meetingServiceMock.getUpcomingMeetings).toHaveBeenCalledOnce();
    });

    it('offers one concrete cell on each axis, never the "all" wildcard', () => {
      setup();

      expect(component.groupOptions).not.toContain(GroupVisibility.ALL);
      expect(component.sectorOptions).not.toContain(SectorVisibility.ALL);
      expect(component.groupOptions).toHaveLength(4);
      expect(component.sectorOptions).toHaveLength(4);
    });

    it('lists the meetings she has already scheduled', () => {
      setup({
        getUpcomingMeetings: vi.fn().mockReturnValue(of([makeMeeting({ title: 'מפגש ראשון' })])),
      });

      expect(text()).toContain('מפגש ראשון');
      expect(
        element().querySelector<HTMLAnchorElement>('.upcoming__item-join')?.getAttribute('href'),
      ).toBe('https://meet.google.com/abc-defg-hij');
    });
  });

  describe('the one-time consent step', () => {
    it('sends her to the URL the server built, and blocks submitting until she is back', () => {
      setup({ getCalendarStatus: vi.fn().mockReturnValue(of(NOT_CONNECTED)) });

      expect(component.needsConsent()).toBe(true);
      expect(
        element().querySelector<HTMLAnchorElement>('.consent__connect')?.getAttribute('href'),
      ).toBe(AUTH_URL);
      expect(submitButton().disabled).toBe(true);
    });

    it('is not shown once the calendar is linked', () => {
      setup();

      expect(component.needsConsent()).toBe(false);
      expect(element().querySelector('.consent')).toBeNull();
      expect(submitButton().disabled).toBe(false);
    });

    /**
     * A failed status request is not a "no": the step is not offered on the
     * absence of an answer, and the form is not held shut by one either.
     */
    it('neither offers the step nor blocks the form when the status request fails', () => {
      setup({ getCalendarStatus: vi.fn().mockReturnValue(throwError(() => ({ status: 500 }))) });

      expect(component.calendarStatus()).toBeNull();
      expect(component.needsConsent()).toBe(false);
      expect(submitButton().disabled).toBe(false);
      expect(text()).toContain('בדיקת החיבור ליומן נכשלה');
    });
  });

  describe('scheduling', () => {
    it('sends a timestamp that states its zone', () => {
      setup();
      fillForm('2030-05-01T14:30');

      component.submit();

      // The input holds local wall-clock time; what goes out is the instant.
      expect(meetingServiceMock.createMeeting).toHaveBeenCalledWith({
        title: 'מפגש תמיכה',
        scheduled_at: new Date('2030-05-01T14:30').toISOString(),
        group_visibility: GroupVisibility.WIDOWS,
        sector_visibility: SectorVisibility.HASIDIC,
      });
    });

    it('confirms, and reloads what is scheduled', () => {
      setup();
      fillForm();

      component.submit();
      fixture.detectChanges();

      expect(component.successKey()).toBe('meetings.schedule.success');
      expect(text()).toContain('הפגישה נקבעה וההכרזה פורסמה בפורום.');
      expect(meetingServiceMock.getUpcomingMeetings).toHaveBeenCalledTimes(2);
    });

    it('clears the title and the time but keeps the cell, for the next one', () => {
      setup();
      fillForm();

      component.submit();

      expect(component.form.controls.title.value).toBe('');
      expect(component.form.controls.scheduled_at.value).toBe('');
      expect(component.form.controls.group_visibility.value).toBe(GroupVisibility.WIDOWS);
    });

    it('sends nothing while the form is incomplete', () => {
      setup();
      component.form.patchValue({ title: '', scheduled_at: '' });

      component.submit();

      expect(meetingServiceMock.createMeeting).not.toHaveBeenCalled();
      expect(component.form.controls.title.touched).toBe(true);
    });

    it('refuses a time that has already passed', () => {
      setup();
      fillForm('2020-01-01T10:00');

      expect(component.form.controls.scheduled_at.errors).toEqual({ pastDateTime: true });

      component.submit();

      expect(meetingServiceMock.createMeeting).not.toHaveBeenCalled();
    });

    /**
     * A successful schedule empties the form, which makes it invalid. Pressing
     * the button again — a second thought, or a double press — must not leave
     * the confirmation standing over the complaint that there is nothing to
     * schedule.
     */
    it('takes the confirmation down before complaining about an empty form', () => {
      setup();
      fillForm();
      component.submit();
      fixture.detectChanges();
      expect(text()).toContain('הפגישה נקבעה וההכרזה פורסמה בפורום.');

      component.submit();
      fixture.detectChanges();

      expect(component.successKey()).toBe('');
      expect(text()).not.toContain('הפגישה נקבעה וההכרזה פורסמה בפורום.');
      expect(meetingServiceMock.createMeeting).toHaveBeenCalledOnce();
    });

    it('takes a stale failure down too, rather than showing it beside a fresh one', () => {
      setup({
        createMeeting: vi.fn().mockReturnValue(throwError(() => ({ status: 500 }))),
      });
      fillForm();
      component.submit();
      fixture.detectChanges();
      expect(text()).toContain('תזמון הפגישה נכשל');

      component.form.patchValue({ title: '', scheduled_at: '' });
      component.submit();
      fixture.detectChanges();

      expect(component.error()).toEqual({ key: '', text: '' });
      expect(text()).not.toContain('תזמון הפגישה נכשל');
    });
  });

  describe('a refusal on submit', () => {
    /**
     * The 403 for a revoked grant and the 403 for someone else's cell carry
     * translated sentences, not keys. The status is what tells them apart: a
     * revoked credential has been deleted by now.
     */
    it('asks for the status again, and brings the consent step back', () => {
      setup({
        getCalendarStatus: vi
          .fn()
          .mockReturnValueOnce(of(CONNECTED))
          .mockReturnValueOnce(of(NOT_CONNECTED)),
        createMeeting: vi.fn().mockReturnValue(
          throwError(() => ({
            status: 403,
            error: { detail: 'יש לחבר את יומן Google לפני תזמון פגישה' },
          })),
        ),
      });
      fillForm();

      component.submit();
      fixture.detectChanges();

      expect(meetingServiceMock.getCalendarStatus).toHaveBeenCalledTimes(2);
      expect(component.needsConsent()).toBe(true);
      // And the server's own sentence is what she reads.
      expect(text()).toContain('יש לחבר את יומן Google לפני תזמון פגישה');
    });

    /**
     * The 403's sentence is the only one that says *which* of the two things
     * went wrong. A status check that fails on top of it must not overwrite
     * that with our vaguer "checking the calendar link failed".
     */
    it('keeps the 403 sentence when the status check fails on top of it', () => {
      setup({
        getCalendarStatus: vi
          .fn()
          .mockReturnValueOnce(of(CONNECTED))
          .mockReturnValueOnce(throwError(() => ({ status: 500 }))),
        createMeeting: vi.fn().mockReturnValue(
          throwError(() => ({
            status: 403,
            error: { detail: 'התא הזה אינו בשיוך שלך' },
          })),
        ),
      });
      fillForm();

      component.submit();
      fixture.detectChanges();

      expect(meetingServiceMock.getCalendarStatus).toHaveBeenCalledTimes(2);
      expect(component.error()).toEqual({ key: '', text: 'התא הזה אינו בשיוך שלך' });
      expect(text()).toContain('התא הזה אינו בשיוך שלך');
      expect(text()).not.toContain('בדיקת החיבור ליומן נכשלה');
    });

    it('leaves the status alone on any other failure', () => {
      setup({
        createMeeting: vi.fn().mockReturnValue(throwError(() => ({ status: 500 }))),
      });
      fillForm();

      component.submit();
      fixture.detectChanges();

      expect(meetingServiceMock.getCalendarStatus).toHaveBeenCalledOnce();
      expect(component.error()).toEqual({ key: 'meetings.errors.create_failed', text: '' });
      expect(text()).toContain('תזמון הפגישה נכשל');
    });
  });

  describe('language', () => {
    it('re-renders its own copy, including a failure already on screen', () => {
      setup({ getCalendarStatus: vi.fn().mockReturnValue(of(NOT_CONNECTED)) });
      expect(text()).toContain('חיבור יומן Google');

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      expect(text()).toContain('Connect Google Calendar');
      expect(text()).toContain('Schedule a Google Meet');
      expect(text()).not.toMatch(HEBREW);
    });

    it('does not pin its own text direction — it follows <html dir>', () => {
      setup();

      expect(element().querySelector('.schedule-meeting')?.hasAttribute('dir')).toBe(false);
    });
  });
});
