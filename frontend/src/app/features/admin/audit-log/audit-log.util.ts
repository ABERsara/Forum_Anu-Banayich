/**
 * How an audit log entry's action and time are rendered — once, for both
 * screens that render them: the list (`AuditLogComponent`, ABF-152) and the
 * single-entry dialog (`AuditLogEntryDialogComponent`, ABF-153).
 *
 * The two must say the same thing about the same entry. A row that reads
 * "השעיית משתמש/ת, 15:00" has to open onto a dialog that says so too, and if
 * the fallback for an unknown action or the reading of the timestamp ever
 * changes, it changes here and both follow.
 *
 * It lives in the feature folder because only this feature needs it
 * (CONTRIBUTING §3) — the same reasoning that keeps `../action-message.ts`
 * next to the screens that use it.
 */

import { AUDIT_ACTION_LABELS } from '../../../core/constants';
import { LabelService } from '../../../core/i18n/label.service';
import { AuditLogEntry } from '../../../core/models';
import { utcIso } from '../../../core/utils/utc-date.util';

/**
 * The action in the reader's language.
 *
 * Through LabelService rather than the template pipe because of the second
 * branch: an action the server has and this build's `AuditAction` does not
 * has no key to pipe, and the raw wire value is a better answer than a blank
 * one — an audit log that quietly omits what happened is worse than one that
 * says `some_new_action`. The LabelService read is what keeps the first
 * branch following a language switch (CONTRIBUTING §6, ABF-128).
 */
export function auditActionLabel(
  entry: Pick<AuditLogEntry, 'action_type'>,
  labels: LabelService,
): string {
  const key = AUDIT_ACTION_LABELS[entry.action_type];
  return key ? labels.label(key) : entry.action_type;
}

/**
 * The entry's timestamp as an *instant*, ready for the date pipe.
 *
 * It arrives as naive UTC — `2026-09-01T12:00:00`, no offset — and the date
 * pipe reads a string without one as a local wall clock, so an admin in
 * Israel would be shown 12:00 for something that happened at 15:00 her
 * time. On an audit log that is not cosmetic: the whole point is to say
 * when, and this is a record that may be read back in a legal proceeding
 * (see `core/utils/utc-date.util.ts`).
 */
export function auditOccurredAt(entry: Pick<AuditLogEntry, 'timestamp'>): string {
  return utcIso(entry.timestamp);
}
