import { DatePipe } from '@angular/common';
import {
  Component,
  ElementRef,
  Injector,
  afterNextRender,
  computed,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { TranslocoPipe } from '@jsverse/transloco';

import { GROUP_VISIBILITY_LABELS, SECTOR_VISIBILITY_LABELS } from '../../../core/constants';
import { Meeting, MeetingUpdate } from '../../../core/models';
import { AuthService } from '../../../core/services/auth.service';
import { MeetingService } from '../../../core/services/meeting.service';
import { AdviceError, NO_ERROR, adviceErrorFrom } from '../advice-error';
import {
  TITLE_MAX_LENGTH,
  TITLE_MIN_LENGTH,
  futureDateTimeUnless,
  toLocalInputValue,
} from '../meeting-form';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';

/**
 * One meeting in the professional's list of meetings ahead, with the two
 * things its creator can do to it (ABF-163): edit the title or the time, and
 * cancel it.
 *
 * This is where those controls live, rather than on the forum announcement,
 * because this is where the creator sees her meetings. The forum feed is a
 * USER/ADMIN screen (`GET /forum/posts` answers 403 to a professional), so a
 * button on the announcement would be drawn for nobody who could press it.
 * The announcement is the other half of the ticket: it shows the result —
 * the new title and time, or "cancelled" with no way in — to the cell.
 *
 * The buttons are drawn for the meeting's creator only. Today that is every
 * meeting this list holds, because the server lists a professional only the
 * meetings she convened; the check is here so that stays true if the list
 * ever shows more, and the server refuses everyone else with a 403 anyway.
 *
 * A component of its own so the scheduling screen keeps one job. It reports
 * back through outputs and keeps nothing of the list: `updated` and
 * `cancelled` tell the parent to reload — an edit can move a meeting in the
 * list, and a cancelled one leaves it — and `refused` tells it a 403 came
 * back, which may mean her calendar grant was revoked (see the parent's
 * `onCalendarRefused`).
 */
@Component({
  selector: 'app-upcoming-meeting',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    DatePipe,
    TranslocoPipe,
    ConfirmDialogComponent,
    ErrorDisplayComponent,
  ],
  templateUrl: './upcoming-meeting.component.html',
  styleUrl: './upcoming-meeting.component.scss',
})
export class UpcomingMeetingComponent {
  private readonly fb = inject(FormBuilder);
  private readonly meetings = inject(MeetingService);
  private readonly authService = inject(AuthService);
  private readonly injector = inject(Injector);

  readonly meeting = input.required<Meeting>();

  /** The meeting as the server now has it. The parent reloads its list. */
  readonly updated = output<Meeting>();
  /** The id of the meeting that was just cancelled. */
  readonly cancelled = output<string>();
  /** An edit or a cancel came back 403. */
  readonly refused = output<void>();

  readonly groupLabels = GROUP_VISIBILITY_LABELS;
  readonly sectorLabels = SECTOR_VISIBILITY_LABELS;
  readonly titleMaxLength = TITLE_MAX_LENGTH;

  readonly form = this.fb.nonNullable.group({
    title: [
      '',
      [
        Validators.required,
        Validators.minLength(TITLE_MIN_LENGTH),
        Validators.maxLength(TITLE_MAX_LENGTH),
      ],
    ],
    scheduled_at: ['', Validators.required],
  });

  readonly isEditing = signal(false);
  readonly isSaving = signal(false);
  readonly isCancelling = signal(false);
  readonly showCancelConfirm = signal(false);
  /** What went wrong, as a key of ours or a sentence the API sent. */
  readonly error = signal<AdviceError>(NO_ERROR);

  /** Edit and cancel are hers alone — see the class comment. */
  readonly canManage = computed(
    () => this.authService.currentUser()?.id === this.meeting().creator.id,
  );

  /** One request at a time: no cancelling a meeting halfway through saving it. */
  readonly isBusy = computed(() => this.isSaving() || this.isCancelling());

  /** The earliest value the picker offers: now, on the viewer's own clock. */
  readonly minDateTime = toLocalInputValue(new Date());

  /**
   * The time the edit form opened with, in the input's own shape. An
   * unchanged value is neither validated as "must be in the future" nor sent
   * — see {@link futureDateTimeUnless}.
   */
  private originalWhen = '';

  private readonly titleInput = viewChild<ElementRef<HTMLInputElement>>('titleInput');

  startEditing(): void {
    const meeting = this.meeting();
    this.error.set(NO_ERROR);
    this.originalWhen = toLocalInputValue(new Date(meeting.scheduled_at));
    this.form.controls.scheduled_at.setValidators([
      Validators.required,
      futureDateTimeUnless(this.originalWhen),
    ]);
    this.form.reset({ title: meeting.title, scheduled_at: this.originalWhen });
    this.isEditing.set(true);
    // The button she pressed is gone once the form replaces it. Without
    // moving focus, a keyboard or screen-reader user is left on nothing.
    afterNextRender(() => this.titleInput()?.nativeElement.focus(), {
      injector: this.injector,
    });
  }

  stopEditing(): void {
    this.error.set(NO_ERROR);
    this.isEditing.set(false);
  }

  save(): void {
    this.error.set(NO_ERROR);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const meeting = this.meeting();
    const { title, scheduled_at } = this.form.getRawValue();
    // Only what changed is sent: the server leaves an absent field as it is,
    // and refuses an empty body.
    const changes: MeetingUpdate = {};
    if (title !== meeting.title) changes.title = title;
    if (scheduled_at !== this.originalWhen) {
      // Local wall-clock time in, the instant out — the same conversion the
      // scheduling form makes, for the same reason.
      changes.scheduled_at = new Date(scheduled_at).toISOString();
    }
    if (Object.keys(changes).length === 0) {
      this.isEditing.set(false);
      return;
    }

    this.isSaving.set(true);
    this.meetings.updateMeeting(meeting.id, changes).subscribe({
      next: (saved) => {
        this.isSaving.set(false);
        this.isEditing.set(false);
        this.updated.emit(saved);
      },
      error: (err: unknown) => {
        this.isSaving.set(false);
        this.error.set(adviceErrorFrom(err, 'meetings.errors.update_failed'));
        this.reportRefusal(err);
      },
    });
  }

  askToCancel(): void {
    this.error.set(NO_ERROR);
    this.showCancelConfirm.set(true);
  }

  onCancelDismissed(): void {
    this.showCancelConfirm.set(false);
  }

  onCancelConfirmed(): void {
    const meeting = this.meeting();
    this.showCancelConfirm.set(false);
    this.isCancelling.set(true);
    this.meetings.cancelMeeting(meeting.id).subscribe({
      next: () => {
        this.isCancelling.set(false);
        this.cancelled.emit(meeting.id);
      },
      error: (err: unknown) => {
        this.isCancelling.set(false);
        this.error.set(adviceErrorFrom(err, 'meetings.errors.cancel_failed'));
        this.reportRefusal(err);
      },
    });
  }

  /**
   * A 403 is either "not yours" or a calendar grant Google no longer honours,
   * and both arrive as finished sentences. The sentence is shown here; the
   * parent asks for the calendar status, which brings the consent step back
   * if it was the grant.
   */
  private reportRefusal(err: unknown): void {
    if ((err as { status?: number })?.status === 403) {
      this.refused.emit();
    }
  }
}
