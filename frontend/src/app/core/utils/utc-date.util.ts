/**
 * Server timestamps arrive as naive UTC — `2026-08-01T10:00:00`, no offset
 * and no `Z` (see DirectMessage.created_at, which stores
 * `datetime.now(UTC).replace(tzinfo=None)`).
 *
 * Both `new Date(...)` and Angular's date pipe read a date-time string with
 * no offset as *local* time, so those instants render three hours off in
 * Israel. On the chat screen it was visible rather than merely wrong: an
 * optimistic bubble is built from `toISOString()`, which does carry a `Z`, so
 * a message showed one clock time and then jumped to another the moment the
 * stored version replaced it.
 */
const HAS_TIMEZONE = /(?:Z|[+-]\d{2}:?\d{2})$/;

/** The same instant, stated in a form that parses as UTC. */
export function utcIso(value: string): string {
  return HAS_TIMEZONE.test(value) ? value : `${value}Z`;
}
