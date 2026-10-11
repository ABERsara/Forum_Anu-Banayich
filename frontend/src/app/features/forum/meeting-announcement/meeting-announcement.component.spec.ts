/**
 * The body of a meeting announcement.
 *
 * Two rules are worth testing here and are tested nowhere else on the client.
 * When a meeting is over: it is the *end* that decides — start plus duration —
 * so a member a few minutes late still gets a live button, and that is the
 * same rule the server applies when it decides which meetings to list. And
 * what a cancelled meeting looks like (ABF-163): it says so, and offers no way
 * in at all.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';

import { MeetingAnnouncementComponent } from './meeting-announcement.component';
import type { MeetingSummary } from '../../../core/models';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

const MINUTE = 60_000;

/** A meeting whose start is `minutesFromNow` away — negative for the past. */
function makeMeeting(minutesFromNow: number, overrides: Partial<MeetingSummary> = {}) {
  return {
    id: 'meeting-1',
    scheduled_at: new Date(Date.now() + minutesFromNow * MINUTE).toISOString(),
    duration_minutes: 60,
    meet_link: 'https://meet.google.com/abc-defg-hij',
    ...overrides,
  } satisfies MeetingSummary;
}

describe('MeetingAnnouncementComponent', () => {
  let fixture: ComponentFixture<MeetingAnnouncementComponent>;

  function setup(meeting: MeetingSummary, cancelled?: boolean): void {
    TestBed.configureTestingModule({
      imports: [MeetingAnnouncementComponent, translocoTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(MeetingAnnouncementComponent);
    fixture.componentRef.setInput('meeting', meeting);
    if (cancelled !== undefined) fixture.componentRef.setInput('cancelled', cancelled);
    fixture.detectChanges();
  }

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return element().textContent ?? '';
  }

  function joinLink(): HTMLAnchorElement | null {
    return element().querySelector<HTMLAnchorElement>('a.meeting-announcement__join');
  }

  function joinButton(): HTMLButtonElement | null {
    return element().querySelector<HTMLButtonElement>('button.meeting-announcement__join');
  }

  it('offers the way in to a meeting still ahead', () => {
    setup(makeMeeting(30));

    expect(joinLink()?.getAttribute('href')).toBe('https://meet.google.com/abc-defg-hij');
    expect(joinLink()?.getAttribute('rel')).toBe('noopener');
    expect(joinButton()).toBeNull();
  });

  it('still offers it while the meeting is in progress', () => {
    // Started ten minutes ago and runs for an hour: late, not over.
    setup(makeMeeting(-10));

    expect(fixture.componentInstance.hasEnded()).toBe(false);
    expect(joinLink()).not.toBeNull();
  });

  it('disables the button once the meeting has ended, and keeps the announcement', () => {
    // Started ninety minutes ago, so it ended thirty minutes ago.
    setup(makeMeeting(-90));

    expect(fixture.componentInstance.hasEnded()).toBe(true);
    expect(joinLink()).toBeNull();
    expect(joinButton()?.disabled).toBe(true);
    // The announcement does not go away with the button.
    expect(text()).toContain('הפגישה הסתיימה');
    expect(text()).toContain('פגישה');
  });

  it('measures the end from the duration, not from a fixed hour', () => {
    // Started twenty minutes ago, but it was a ten-minute meeting.
    setup(makeMeeting(-20, { duration_minutes: 10 }));

    expect(fixture.componentInstance.hasEnded()).toBe(true);
  });

  /**
   * `scheduled_at` is the one kind of timestamp this API sends with its zone.
   * Read as local wall-clock time, a meeting half an hour ahead would look
   * two and a half hours past in Israel — and its button would be dead.
   */
  it('reads the start as the zoned instant the server sent', () => {
    const inHalfAnHour = new Date(Date.now() + 30 * MINUTE);
    setup(makeMeeting(0, { scheduled_at: inHalfAnHour.toISOString() }));

    expect(fixture.componentInstance.hasEnded()).toBe(false);
  });

  it('translates its own copy and leaves the link alone', () => {
    setup(makeMeeting(-90));
    expect(text()).toContain('הפגישה הסתיימה');

    TestBed.inject(TranslocoService).setActiveLang('en');
    fixture.detectChanges();

    expect(text()).toContain('This meeting has ended');
    expect(text()).not.toMatch(HEBREW);
  });

  describe('once the meeting is cancelled', () => {
    it('says so, and offers no way in — not even a disabled one', () => {
      setup(makeMeeting(30), true);

      expect(text()).toContain('פגישה בוטלה');
      expect(joinLink()).toBeNull();
      expect(joinButton()).toBeNull();
    });

    it('keeps the time it was set for, struck through', () => {
      setup(makeMeeting(30), true);

      expect(
        element()
          .querySelector('.meeting-announcement__when')
          ?.classList.contains('meeting-announcement__when--cancelled'),
      ).toBe(true);
    });

    /** A cancelled meeting never took place, whatever the clock says now. */
    it('reads as cancelled rather than ended once its time has passed', () => {
      setup(makeMeeting(-90), true);

      expect(text()).toContain('פגישה בוטלה');
      expect(text()).not.toContain('הפגישה הסתיימה');
      expect(joinButton()).toBeNull();
    });

    it('is not cancelled unless told so', () => {
      setup(makeMeeting(30));

      expect(text()).not.toContain('פגישה בוטלה');
      expect(joinLink()).not.toBeNull();
    });

    it('translates the word', () => {
      setup(makeMeeting(30), true);

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      expect(text()).toContain('Meeting cancelled');
      expect(text()).not.toMatch(HEBREW);
    });
  });

  it('does not pin its own text direction — it follows <html dir>', () => {
    setup(makeMeeting(30));

    expect(element().querySelector('.meeting-announcement')?.hasAttribute('dir')).toBe(false);
  });
});
