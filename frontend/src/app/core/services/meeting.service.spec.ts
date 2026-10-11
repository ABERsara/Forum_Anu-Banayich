/**
 * The six meeting calls, against `HttpTestingController`.
 *
 * What is worth asserting here is the shape of the *request*, because that is
 * the half the backend contract fixes and the half a component cannot check:
 * the paths — `calendar/status` and `calendar/connect` sit under `/meetings`,
 * where the server declares them before anything with a path parameter — and
 * that the body of a connect carries both the code and the state, since the
 * server verifies the state against the caller and refuses a request without
 * it.
 */

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { MeetingService } from './meeting.service';
import { environment } from '../../../environments/environment';
import { GroupVisibility, SectorVisibility } from '../constants';
import type { CalendarStatus, Meeting } from '../models';

const MEETING: Meeting = {
  id: 'meeting-1',
  title: 'מפגש תמיכה',
  scheduled_at: '2030-05-01T11:30:00Z',
  duration_minutes: 60,
  meet_link: 'https://meet.google.com/abc-defg-hij',
  group_visibility: GroupVisibility.WIDOWS,
  sector_visibility: SectorVisibility.HASIDIC,
  creator: { id: 'pro-1', first_name: 'שרה', last_name: 'לוי' },
  created_at: '2026-10-05T09:00:00Z',
};

const STATUS: CalendarStatus = {
  connected: true,
  connected_at: '2026-10-05T09:00:00Z',
  authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?client_id=x',
};

describe('MeetingService', () => {
  let service: MeetingService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(MeetingService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('schedules a meeting with the body the server expects', () => {
    const body = {
      title: 'מפגש תמיכה',
      scheduled_at: '2030-05-01T11:30:00.000Z',
      group_visibility: GroupVisibility.WIDOWS,
      sector_visibility: SectorVisibility.HASIDIC,
    };

    service.createMeeting(body).subscribe((meeting) => expect(meeting.id).toBe('meeting-1'));

    const req = httpMock.expectOne(`${environment.apiUrl}/meetings`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(body);
    req.flush(MEETING);
  });

  /** Unpaginated, and already filtered by the server — no query string of ours. */
  it('asks for the meetings still ahead without any filter of its own', () => {
    service.getUpcomingMeetings().subscribe((meetings) => expect(meetings).toHaveLength(1));

    const req = httpMock.expectOne(`${environment.apiUrl}/meetings`);
    expect(req.request.method).toBe('GET');
    expect(req.request.params.keys()).toEqual([]);
    req.flush([MEETING]);
  });

  it('reads the calendar status', () => {
    service.getCalendarStatus().subscribe((status) => expect(status.connected).toBe(true));

    const req = httpMock.expectOne(`${environment.apiUrl}/meetings/calendar/status`);
    expect(req.request.method).toBe('GET');
    req.flush(STATUS);
  });

  it('sends both the code and the state when linking a calendar', () => {
    service
      .connectCalendar('google-code', 'signed-state')
      .subscribe((status) => expect(status.connected).toBe(true));

    const req = httpMock.expectOne(`${environment.apiUrl}/meetings/calendar/connect`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ code: 'google-code', state: 'signed-state' });
    req.flush(STATUS);
  });

  /** Only what changes travels: the server leaves an absent field as it is. */
  it('edits a meeting with a PATCH that carries only the changed fields', () => {
    service
      .updateMeeting('meeting-1', { title: 'כותרת חדשה' })
      .subscribe((meeting) => expect(meeting.title).toBe('כותרת חדשה'));

    const req = httpMock.expectOne(`${environment.apiUrl}/meetings/meeting-1`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ title: 'כותרת חדשה' });
    req.flush({ ...MEETING, title: 'כותרת חדשה' });
  });

  it('cancels a meeting with a DELETE on the meeting itself', () => {
    let done = false;
    service.cancelMeeting('meeting-1').subscribe(() => (done = true));

    const req = httpMock.expectOne(`${environment.apiUrl}/meetings/meeting-1`);
    expect(req.request.method).toBe('DELETE');
    req.flush(null, { status: 204, statusText: 'No Content' });
    expect(done).toBe(true);
  });
});
