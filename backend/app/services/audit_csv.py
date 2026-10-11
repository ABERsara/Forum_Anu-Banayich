"""
The audit log as a CSV file (GET /admin/audit-log/export, ABF-161).

This module only turns rows into text. Which rows, in what order and how many
at a time is `audit_service.iter_audit_log_for_export()`'s business; the file
built here is whatever that iterator yields, written out as it arrives.

Who the file is for
-------------------
Not a developer. The ticket names the readers: lawyers and accountants the
organisation shares the log with, opening it in Excel. Everything below
follows from that.

- **UTF-8 with a BOM.** Excel opens a BOM-less CSV in the machine's ANSI code
  page, which turns every Hebrew header into mojibake. The three bytes
  `EF BB BF` at the very start are what tell it otherwise. They are the first
  thing written, before the header row.
- **Hebrew column headers, and the action as Hebrew words.** `user_suspended`
  means nothing to a lawyer; "השעיית משתמש/ת" does. The raw code sits in the
  column beside it, because it is the value the screen's filter takes and the
  one that stays stable if a label is ever reworded.
- **Hebrew regardless of `Accept-Language`.** The headers are not interface
  copy that follows whoever clicked: the file is a document handed to someone
  else, and the people it is handed to read Hebrew. An admin who happens to
  browse in English would otherwise send an Israeli lawyer an English file.
- **The labels are the screen's own.** `ACTION_LABELS` repeats the frontend's
  `constants.audit_action.*` wording in `he.json`, and
  `tests/test_admin_audit_log_export.py` fails if the two ever differ, or if
  an `AuditAction` is added without a label here.
- **Timestamps in UTC, and the header says so.** The stored timestamps are
  naive UTC, and so are the day bounds of the date filter the file was
  exported under — a row dated 23:30 UTC on the 1st belongs to the 1st in
  both. Converting to Israel time would make the file disagree with its own
  filter on every evening row. `YYYY-MM-DD HH:MM:SS` is unambiguous in every
  locale — unlike `01/02`, which is January in one and February in another —
  and sorts chronologically even where Excel keeps it as text, as Hebrew
  Excel opening this file does.
- **`\\r\\n` line endings and minimal quoting** — the `csv` module's `excel`
  dialect, which is the dialect named for exactly this reader.

What is not in the file
-----------------------
`ip_address`. Not as a column, not under a parameter. The decision recorded on
ABF-152 is that no screen exposes it, and the ticket repeats it for the
export: `COLUMNS` is the whole list of what a row can carry, and the IP is
not in it.

Formula injection
-----------------
A cell that starts with `=`, `+`, `-` or `@` is a formula to Excel, not text —
`=HYPERLINK(...)` in an entity id would be a live link in the lawyer's
spreadsheet. Ids are UUIDs and entity types are class names today, but
`details` and the identifiers are stored strings, and this file leaves the
building. So any cell that starts that way is written with a leading `'`,
the OWASP-recommended neutraliser, which Excel shows as text and nothing
else. A cell that starts any other way is written exactly as stored.
"""

import csv
import io
import json
from collections.abc import Iterable, Iterator
from typing import Final

from app.core.constants import AuditAction
from app.models.audit import AuditLog
from app.services.audit_service import EXPORT_BATCH_SIZE

#: What makes Excel read the file as UTF-8 rather than as the local code page.
UTF8_BOM: Final = "﻿"

#: The header row, in the order the screen shows its columns — who, what,
#: when, which entity — with the entry's own id first, as a reference a
#: lawyer can quote back, and `details` last, being the widest.
COLUMNS: Final = (
    "מזהה רשומה",
    "מזהה מבצע/ת הפעולה",
    "פעולה",
    "קוד פעולה",
    "תאריך ושעה (UTC)",
    "סוג ישות",
    "מזהה ישות",
    "פרטים",
)

#: The `פעולה` column — the frontend's `constants.audit_action.*` in he.json,
#: word for word (the export tests compare the two).
ACTION_LABELS: Final[dict[AuditAction, str]] = {
    AuditAction.USER_APPROVED: "אישור הרשמה",
    AuditAction.USER_PARTIALLY_APPROVED: "אישור חלקי של הרשמה",
    AuditAction.USER_REJECTED: "דחיית הרשמה",
    AuditAction.USER_SUSPENDED: "השעיית משתמש/ת",
    AuditAction.USER_CANCELLED: "ביטול חשבון",
    AuditAction.POST_DELETED: "מחיקת פוסט",
    AuditAction.BROADCAST_SENT: "שליחת הודעת מערכת",
    AuditAction.REPORT_DECIDED: "הכרעה בדיווח",
    AuditAction.PROFESSIONAL_ADDED: "הוספת איש/אשת מקצוע",
    AuditAction.PROFESSIONAL_UPDATED: "עדכון איש/אשת מקצוע",
    AuditAction.MODERATOR_ASSIGNED: "מינוי ממונה",
    AuditAction.MODERATOR_UPDATED: "עדכון ממונה",
    AuditAction.MODERATOR_REMOVED: "הסרת ממונה",
    AuditAction.DATA_EXPORTED: "ייצוא נתונים",
    AuditAction.USER_LOGIN: "כניסה למערכת",
    AuditAction.USER_LOGOUT: "יציאה מהמערכת",
    AuditAction.DIRECT_MESSAGE_ACCESS_DENIED: "גישה להודעה פרטית נדחתה",
    AuditAction.DIRECT_MESSAGE_PRUNED: "מחיקת הודעות פרטיות ישנות",
    AuditAction.DIRECT_MESSAGE_REPORTED: "דיווח על הודעה פרטית",
    AuditAction.DIRECT_MESSAGE_REPORT_VIEWED: "צפייה בתוכן הודעה שדווחה",
    AuditAction.USER_RESTRICTED: "החלת הגבלה אוטומטית",
    AuditAction.AGENT_CONVERSATION: "שיחה עם סוכן AI",
    AuditAction.AGENT_CONVERSATION_ACCESS_DENIED: "גישה לשיחת סוכן נדחתה",
    AuditAction.MEETING_CREATED: "קביעת פגישה",
    AuditAction.PROFILE_UPDATED: "עדכון פרופיל",
}

#: The characters that make Excel (and LibreOffice, and Sheets) evaluate a
#: cell rather than display it. Tab and carriage return are on OWASP's list
#: because some importers strip them and then see the `=` behind.
_FORMULA_TRIGGERS: Final = ("=", "+", "-", "@", "\t", "\r")

TIMESTAMP_FORMAT: Final = "%Y-%m-%d %H:%M:%S"


def _cell(value: str) -> str:
    """One cell's text, with a formula neutralised and anything else untouched."""
    return f"'{value}" if value.startswith(_FORMULA_TRIGGERS) else value


def _row(entry: AuditLog) -> list[str]:
    """
    One entry as the eight cells of `COLUMNS`.

    An action this build has no label for — a value added to the enum on a
    branch that forgot this map — is written as its code rather than left
    blank, the same fallback the screen uses: an audit file that silently
    omits what happened is worse than one that names it in English.

    `details` is JSON with the Hebrew left readable (`ensure_ascii=False`),
    not escaped into `\\u05d0` sequences nobody at the receiving end can read.
    """
    action = AuditAction(entry.action)
    details = (
        ""
        if entry.details is None
        else json.dumps(entry.details, ensure_ascii=False, default=str)
    )
    return [
        _cell(value)
        for value in (
            entry.id,
            entry.actor_id,
            ACTION_LABELS.get(action, action.value),
            action.value,
            entry.timestamp.strftime(TIMESTAMP_FORMAT),
            entry.entity_type,
            entry.entity_id,
            details,
        )
    ]


def csv_chunks(
    entries: Iterable[AuditLog], batch_size: int = EXPORT_BATCH_SIZE
) -> Iterator[str]:
    """
    The file, as text chunks of up to `batch_size` rows, for StreamingResponse.

    The first chunk opens with the BOM and the header row, so an export that
    matched nothing is still a valid file: the headers and no rows, which is
    what Excel should show for "no entries match these filters".

    Chunks of a batch rather than one per row: Starlette runs a sync iterator
    one `next()` per worker-thread hop, and fifty thousand hops for fifty
    thousand rows is the slow way to send a file. The batch size is the
    query's, so one chunk is one round of the cursor.

    `entries` is consumed lazily — a row is formatted only once the one before
    it has been, and a chunk is handed on before the next is read — so this
    never holds more than one batch, whatever the log's size.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, dialect="excel")

    buffer.write(UTF8_BOM)
    writer.writerow(COLUMNS)

    pending = 0
    for entry in entries:
        writer.writerow(_row(entry))
        pending += 1
        if pending == batch_size:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            pending = 0

    # The tail — or, for an empty export, the BOM and the header row alone.
    # Empty only when the last row closed a batch exactly, and then there is
    # nothing left to send.
    if buffer.tell():
        yield buffer.getvalue()
