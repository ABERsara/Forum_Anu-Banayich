import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import {
  GROUP_VISIBILITY_LABELS,
  GroupVisibility,
  SECTOR_VISIBILITY_LABELS,
  SectorVisibility,
} from '../../../core/constants';
import { CalendarStatus, Meeting } from '../../../core/models';
import { MeetingService } from '../../../core/services/meeting.service';
import { AdviceError, NO_ERROR, adviceErrorFrom } from '../advice-error';
import {
  TITLE_MAX_LENGTH,
  TITLE_MIN_LENGTH,
  futureDateTime,
  toLocalInputValue,
} from '../meeting-form';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';
import { UpcomingMeetingComponent } from '../upcoming-meeting/upcoming-meeting.component';

/**
 * A professional schedules a Google Meet for one of her cells.
 *
 * Two things make this more than a form. The first is consent: creating the
 * event needs a Google Calendar authorisation that logging in does not grant,
 * so the screen asks `GET /meetings/calendar/status` on the way in and sends
 * her to Google once, through the `authorization_url` that answer carries.
 *
 * The second is that a 403 on submit cannot be read. "Your calendar is not
 * linked" and "that cell is not yours" both come back as finished sentences
 * rather than keys, so the screen asks for the status again instead of
 * guessing: a grant that was revoked or expired has been deleted by then, and
 * the answer says `connected: false`.
 */
@Component({
  selector: 'app-schedule-meeting',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
    UpcomingMeetingComponent,
  ],
  templateUrl: './schedule-meeting.component.html',
  styleUrl: './schedule-meeting.component.scss',
})
export class ScheduleMeetingComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly meetings = inject(MeetingService);

  readonly groupLabels = GROUP_VISIBILITY_LABELS;
  readonly sectorLabels = SECTOR_VISIBILITY_LABELS;
  readonly titleMaxLength = TITLE_MAX_LENGTH;

  /**
   * One concrete cell, so the "all" wildcard is left out of both lists: the
   * server refuses it with a 422, because a meeting is a support session for
   * one group of people who share a situation, not a broadcast.
   *
   * Every other cell is offered, not only the ones in her assignment — which
   * `GET /users/me` does not carry (UserProfile has no `professional_groups`
   * or `professional_sectors`). A cell outside it comes back as a 403 whose
   * sentence says exactly that, and it is shown as it came.
   */
  readonly groupOptions = Object.values(GroupVisibility).filter(
    (value) => value !== GroupVisibility.ALL,
  );
  readonly sectorOptions = Object.values(SectorVisibility).filter(
    (value) => value !== SectorVisibility.ALL,
  );

  /** The earliest value the picker offers: now, on the viewer's own clock. */
  readonly minDateTime = toLocalInputValue(new Date());

  readonly form = this.fb.nonNullable.group({
    title: [
      '',
      [
        Validators.required,
        Validators.minLength(TITLE_MIN_LENGTH),
        Validators.maxLength(TITLE_MAX_LENGTH),
      ],
    ],
    scheduled_at: ['', [Validators.required, futureDateTime]],
    group_visibility: [this.groupOptions[0], Validators.required],
    sector_visibility: [this.sectorOptions[0], Validators.required],
  });

  readonly calendarStatus = signal<CalendarStatus | null>(null);
  readonly isCheckingStatus = signal(false);
  readonly upcoming = signal<Meeting[]>([]);
  readonly isLoadingUpcoming = signal(false);
  readonly isSubmitting = signal(false);
  /** What went wrong, as a key of ours or a sentence the API sent. */
  readonly error = signal<AdviceError>(NO_ERROR);
  /** Held as a key and piped in the template, so it follows a language switch. */
  readonly successKey = signal('');
  /**
   * The confirmation for an edit or a cancellation in the list (ABF-163).
   * Its own signal rather than `successKey`, because it belongs beside the
   * list, not above the form — and only one of the two is ever shown: each
   * action takes the other's confirmation down.
   */
  readonly upcomingSuccessKey = signal('');

  /**
   * Whether she still has to authorise Google Calendar. False while the status
   * is unknown — the consent step appears on a definite "no", never on the
   * absence of an answer.
   */
  readonly needsConsent = computed(() => this.calendarStatus()?.connected === false);

  ngOnInit(): void {
    this.loadCalendarStatus();
    this.loadUpcoming();
  }

  submit(): void {
    // Cleared before the form is judged, not after: a successful schedule
    // leaves the form empty and therefore invalid, so a second press would
    // otherwise show "the meeting was scheduled" above the complaint that
    // there is nothing to schedule.
    this.error.set(NO_ERROR);
    this.successKey.set('');
    this.upcomingSuccessKey.set('');

    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const { title, scheduled_at, group_visibility, sector_visibility } = this.form.getRawValue();
    this.isSubmitting.set(true);

    this.meetings
      .createMeeting({
        title,
        // The input holds local wall-clock time with no zone. Sent as it is,
        // it would be read as UTC and book the meeting three hours late in
        // Israel, so the zone is stated here.
        scheduled_at: new Date(scheduled_at).toISOString(),
        group_visibility,
        sector_visibility,
      })
      .subscribe({
        next: () => {
          this.successKey.set('meetings.schedule.success');
          this.isSubmitting.set(false);
          // The cell is left as it was: a professional scheduling a series for
          // the same group should not have to pick it again.
          this.form.patchValue({ title: '', scheduled_at: '' });
          this.form.controls.title.markAsUntouched();
          this.form.controls.scheduled_at.markAsUntouched();
          this.loadUpcoming();
        },
        error: (err: unknown) => {
          this.error.set(adviceErrorFrom(err, 'meetings.errors.create_failed'));
          this.isSubmitting.set(false);
          // Both kinds of 403 carry a sentence rather than a key, so the
          // status is what tells the screen whether the consent step has to
          // come back. Silent: the 403 already said what went wrong, and a
          // status check that fails on top of it must not replace that
          // sentence with a vaguer one of ours.
          if ((err as { status?: number })?.status === 403) {
            this.loadCalendarStatus({ reportFailure: false });
          }
        },
      });
  }

  /** A meeting in the list was edited: it may have moved, so the list is read again. */
  onMeetingUpdated(): void {
    this.successKey.set('');
    this.upcomingSuccessKey.set('meetings.upcoming.updated');
    this.loadUpcoming();
  }

  /** A meeting in the list was cancelled: it leaves the list on the next read. */
  onMeetingCancelled(): void {
    this.successKey.set('');
    this.upcomingSuccessKey.set('meetings.upcoming.cancelled');
    this.loadUpcoming();
  }

  /**
   * An edit or a cancel came back 403. The same check as after a refused
   * submit, for the same reason: a grant Google revoked has been deleted by
   * now, and the status brings the consent step back. Silent, so the row's
   * own sentence survives a failing check.
   */
  onCalendarRefused(): void {
    this.loadCalendarStatus({ reportFailure: false });
  }

  /**
   * Ask whether the calendar is linked.
   *
   * `reportFailure` is false for the check that follows a 403, whose own
   * sentence is the better explanation and must survive.
   */
  private loadCalendarStatus({ reportFailure = true } = {}): void {
    this.isCheckingStatus.set(true);
    this.meetings.getCalendarStatus().subscribe({
      next: (status) => {
        this.calendarStatus.set(status);
        this.isCheckingStatus.set(false);
      },
      error: (err: unknown) => {
        // Left unknown rather than assumed either way: a failed request
        // neither offers the consent step nor blocks the form.
        this.calendarStatus.set(null);
        if (reportFailure) {
          this.error.set(adviceErrorFrom(err, 'meetings.errors.status_failed'));
        }
        this.isCheckingStatus.set(false);
      },
    });
  }

  private loadUpcoming(): void {
    this.isLoadingUpcoming.set(true);
    this.meetings.getUpcomingMeetings().subscribe({
      next: (meetings) => {
        this.upcoming.set(meetings);
        this.isLoadingUpcoming.set(false);
      },
      error: (err: unknown) => {
        this.error.set(adviceErrorFrom(err, 'meetings.errors.load_upcoming_failed'));
        this.isLoadingUpcoming.set(false);
      },
    });
  }
}
