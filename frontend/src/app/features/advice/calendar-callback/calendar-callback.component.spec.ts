/**
 * Where Google returns the browser after the calendar consent screen.
 *
 * Three things matter here. The page posts exactly what it arrived with, it
 * clears those values out of the address bar afterwards — the code is
 * single-use, and a reload would spend it a second time — and it says which of
 * the three endings happened: linked, declined, or failed.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { CalendarCallbackComponent } from './calendar-callback.component';
import type { CalendarStatus } from '../../../core/models';
import { MeetingService } from '../../../core/services/meeting.service';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

const CONNECTED: CalendarStatus = {
  connected: true,
  connected_at: '2026-10-05T09:00:00Z',
  authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?client_id=x',
};

describe('CalendarCallbackComponent', () => {
  let fixture: ComponentFixture<CalendarCallbackComponent>;
  let component: CalendarCallbackComponent;
  let meetingServiceMock: { connectCalendar: ReturnType<typeof vi.fn> };
  let navigateSpy: ReturnType<typeof vi.fn>;

  function setup(queryParams: Record<string, string>, connect = of(CONNECTED)): void {
    meetingServiceMock = { connectCalendar: vi.fn().mockReturnValue(connect) };
    navigateSpy = vi.fn();

    TestBed.configureTestingModule({
      imports: [CalendarCallbackComponent, translocoTesting()],
      providers: [
        { provide: MeetingService, useValue: meetingServiceMock },
        { provide: Router, useValue: { navigate: navigateSpy } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap(queryParams) } },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(CalendarCallbackComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  describe('a consent that went through', () => {
    it('hands the code and the state it arrived with to the server', () => {
      setup({ code: 'google-code', state: 'signed-state' });

      expect(meetingServiceMock.connectCalendar).toHaveBeenCalledWith(
        'google-code',
        'signed-state',
      );
      expect(component.status()).toBe('connected');
      expect(text()).toContain('היומן חובר');
    });

    it('clears the code out of the address bar, replacing the entry', () => {
      setup({ code: 'google-code', state: 'signed-state' });

      expect(navigateSpy).toHaveBeenCalledWith(
        [],
        expect.objectContaining({ queryParams: {}, replaceUrl: true }),
      );
    });
  });

  describe('a consent she declined', () => {
    it('says so, and posts nothing', () => {
      setup({ error: 'access_denied' });

      expect(component.status()).toBe('denied');
      expect(meetingServiceMock.connectCalendar).not.toHaveBeenCalled();
      expect(text()).toContain('ההרשאה לא ניתנה');
    });

    it('clears the error out of the address bar too', () => {
      setup({ error: 'access_denied' });

      expect(navigateSpy).toHaveBeenCalledWith(
        [],
        expect.objectContaining({ queryParams: {}, replaceUrl: true }),
      );
    });
  });

  describe('a return that cannot be completed', () => {
    it('refuses to post when the code is missing', () => {
      setup({ state: 'signed-state' });

      expect(meetingServiceMock.connectCalendar).not.toHaveBeenCalled();
      expect(component.status()).toBe('failed');
      expect(component.error()).toEqual({ key: 'meetings.callback.missing_code', text: '' });
    });

    it('refuses to post when the state is missing', () => {
      setup({ code: 'google-code' });

      expect(meetingServiceMock.connectCalendar).not.toHaveBeenCalled();
      expect(component.status()).toBe('failed');
    });

    it('treats any other error Google sends as a failure, not a refusal', () => {
      setup({ error: 'invalid_scope' });

      expect(component.status()).toBe('failed');
      expect(meetingServiceMock.connectCalendar).not.toHaveBeenCalled();
    });

    /** The server's `detail` is a finished sentence — shown as it came. */
    it('shows the reason the server gave', () => {
      setup(
        { code: 'spent-code', state: 'signed-state' },
        throwError(() => ({ status: 400, error: { detail: 'הקוד שהתקבל מגוגל אינו תקף' } })),
      );

      expect(component.status()).toBe('failed');
      expect(component.error()).toEqual({ key: '', text: 'הקוד שהתקבל מגוגל אינו תקף' });
      expect(text()).toContain('הקוד שהתקבל מגוגל אינו תקף');
    });

    it('falls back to our own key when the server sent no detail', () => {
      setup(
        { code: 'c', state: 's' },
        throwError(() => ({ status: 500 })),
      );

      expect(component.error()).toEqual({ key: 'meetings.errors.connect_failed', text: '' });
      expect(text()).toContain('חיבור היומן נכשל');
    });
  });

  /** Our copy is held as a key, so it follows a language switch. */
  it('re-renders its own copy in English', () => {
    setup({ error: 'access_denied' });
    expect(text()).toContain('ההרשאה לא ניתנה');

    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();

    expect(text()).toContain('Permission was not granted');
    expect(text()).not.toMatch(HEBREW);
  });
});
