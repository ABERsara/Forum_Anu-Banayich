import { DatePipe } from '@angular/common';
import { Component, input } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';

import { MeetingSummary } from '../../../core/models';

/**
 * The body of a MEETING announcement: when it starts, and the way in.
 *
 * Rendered by both forum screens — the list card and the post page — which is
 * why it is a component rather than markup in each of them: the rule for when
 * a meeting is over decides whether the join button is live, and two copies of
 * that rule is one copy too many. It stays inside `features/forum/` rather
 * than moving to `shared/components/`: both callers are this feature's, and
 * nothing outside it draws an announcement.
 *
 * Dumb by design — an input and no injection — so each caller keeps its own
 * heading, author line and controls above it.
 */
@Component({
  selector: 'app-meeting-announcement',
  standalone: true,
  imports: [DatePipe, TranslocoPipe],
  templateUrl: './meeting-announcement.component.html',
  styleUrl: './meeting-announcement.component.scss',
})
export class MeetingAnnouncementComponent {
  readonly meeting = input.required<MeetingSummary>();

  /**
   * Whether the professional who scheduled it called it off (ABF-163) — the
   * post's `cancelled_at`, which travels on the post rather than on
   * `meeting`. A cancelled announcement says so and offers no way in: its
   * Google event is gone, and a button, even a disabled one, would read as a
   * meeting that might still happen.
   */
  readonly cancelled = input(false);

  /**
   * Whether the meeting is over: its start plus its duration, not its start.
   * A member a few minutes late can still find her way in, which is the same
   * rule `meeting_service.get_visible_meetings()` applies on the server.
   *
   * A method rather than a `computed`, so it is re-read on every change
   * detection pass instead of being cached against an input that never
   * changes. Deliberately not on a timer: the announcement of a meeting that
   * ends while the page sits open goes stale until the next render, and a
   * forum page left open through exactly that minute does not justify an
   * interval ticking behind every card.
   *
   * `scheduled_at` carries its zone (`...Z`), so `new Date` reads the instant
   * the server meant rather than the viewer's wall clock.
   */
  hasEnded(): boolean {
    const meeting = this.meeting();
    const endsAt = new Date(meeting.scheduled_at).getTime() + meeting.duration_minutes * 60_000;
    return endsAt <= Date.now();
  }
}
