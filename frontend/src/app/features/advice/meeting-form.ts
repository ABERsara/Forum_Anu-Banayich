/**
 * The rules a meeting's title and time follow on the way in, shared by the
 * screen that schedules a meeting and the one that edits it (ABF-163).
 *
 * One copy, because both forms send to endpoints that apply the same rules
 * (MeetingCreate and MeetingUpdate in backend/app/schemas/meeting.py), and two
 * copies here would be two places to forget when one of them changes.
 */

import { AbstractControl, ValidatorFn } from '@angular/forms';

/** Mirrors the title Field in backend/app/schemas/meeting.py. */
export const TITLE_MIN_LENGTH = 2;
export const TITLE_MAX_LENGTH = 256;

/** `2026-10-05T14:30`, the shape a `datetime-local` input reads and writes. */
export function toLocalInputValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  const day = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  return `${day}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * A meeting has to start in the future — the server answers 422 otherwise.
 *
 * Checked against the clock at the moment of editing, so a value that was
 * valid when it was typed and went stale while the form sat open passes here
 * and is caught by the server, whose sentence is then shown as it came. The
 * `min` attribute on the input states the same rule to the browser; neither is
 * a substitute for the server's.
 */
export function futureDateTime(control: AbstractControl): { pastDateTime: true } | null {
  const value = control.value as string;
  if (!value) return null;
  return new Date(value).getTime() > Date.now() ? null : { pastDateTime: true };
}

/**
 * {@link futureDateTime}, except for the value the field started with.
 *
 * For the edit form. A meeting already in progress may still have its title
 * corrected, and its start — now in the past — comes back into the form
 * untouched. Only a time she actually changed has to be in the future,
 * because only a changed time is sent.
 */
export function futureDateTimeUnless(original: string): ValidatorFn {
  return (control) => (control.value === original ? null : futureDateTime(control));
}
