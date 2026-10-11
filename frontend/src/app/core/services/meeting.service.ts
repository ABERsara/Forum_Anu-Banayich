/**
 * Scheduled meetings, and the Google Calendar authorisation that makes
 * scheduling possible.
 *
 * Six calls, no logic: who may schedule, which cells she may convene and
 * which meetings she may see are all the server's decisions, and a copy of
 * any of them here would be a second rule to keep in step with the first.
 */

import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { CalendarStatus, Meeting, MeetingCreate, MeetingUpdate } from '../models';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class MeetingService {
  private readonly api = inject(ApiService);

  /**
   * Schedule a meeting and publish its announcement. Professionals only.
   *
   * `data.scheduled_at` must carry its zone — `new Date(...).toISOString()`.
   * A 403 means either that her calendar is not (or no longer) linked, or
   * that the cell is outside her assignment; the `detail` is translated text
   * rather than a key, so the two cannot be told apart from the body.
   * {@link getCalendarStatus} is the signal instead — a revoked grant has
   * been deleted by the time the 403 arrives, so it then reports
   * `connected: false`.
   */
  createMeeting(data: MeetingCreate): Observable<Meeting> {
    return this.api.post<Meeting>('/meetings', data);
  }

  /**
   * Meetings that have not finished yet and that the caller may see.
   *
   * Unpaginated, and already filtered by the server: a professional gets the
   * meetings she convened, a member the ones published to her cell. Past
   * meetings drop out of here and leave their announcement in the forum.
   */
  getUpcomingMeetings(): Observable<Meeting[]> {
    return this.api.get<Meeting[]>('/meetings');
  }

  /**
   * Change a meeting's title, its time, or both. Its creator only (ABF-163).
   *
   * The server updates the forum announcement and the Google Calendar event
   * along with the meeting; the Meet link does not change. A 403 is either
   * "not yours" or a calendar grant that was revoked, told apart the same
   * way as on {@link createMeeting}: by asking {@link getCalendarStatus}.
   */
  updateMeeting(id: string, data: MeetingUpdate): Observable<Meeting> {
    return this.api.patch<Meeting>(`/meetings/${id}`, data);
  }

  /**
   * Call a meeting off. Its creator only (ABF-163).
   *
   * Deletes the Google Calendar event and marks the announcement as
   * cancelled; the announcement stays in the forum. Answers 204 with no
   * body, and again 204 for a meeting already cancelled.
   */
  cancelMeeting(id: string): Observable<void> {
    return this.api.delete<void>(`/meetings/${id}`);
  }

  /** Whether this professional has authorised calendar access, and where to send her if not. */
  getCalendarStatus(): Observable<CalendarStatus> {
    return this.api.get<CalendarStatus>('/meetings/calendar/status');
  }

  /**
   * Link the calendar Google just authorised, from the return page.
   *
   * Both values are the ones Google put in the query string. The code is
   * single-use: posting it twice answers 400, which is why the return page
   * strips it from the URL once this has run.
   */
  connectCalendar(code: string, state: string): Observable<CalendarStatus> {
    return this.api.post<CalendarStatus>('/meetings/calendar/connect', { code, state });
  }
}
