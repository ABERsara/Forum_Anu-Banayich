"""
GET /api/v1/admin/audit-log/export — the filtered audit log as a CSV file
(ABF-161).

Built around the ticket's four acceptance criteria, in order, plus the two
things the criteria rest on:

1. **Non-admin → 403**, for all three other roles, with and without
   parameters — and nothing is written for them either.
2. **The file holds exactly the rows the filtered screen shows.** Not "rows
   that satisfy the filter as this test understands it": every export below
   is compared against what `GET /admin/audit-log` itself returns for the same
   filters, in the same order. If the two endpoints ever disagree, this is
   where it shows.
3. **Excel opens it cleanly**: the BOM bytes, the Hebrew headers, `\\r\\n`,
   quoting that survives commas, quotes and newlines, and no cell Excel would
   run as a formula.
4. **No full-table fetch.** The response body cannot show this, so the SQL
   is captured: the filters are in its WHERE clause, and the rows are read
   with `yield_per`, a batch at a time — a server-side cursor on Postgres,
   checked against a real one when `TEST_POSTGRES_URL` is set.

And underneath: the two endpoints take the same six filters (compared through
the OpenAPI schema, so a parameter added to one alone fails here), the route
is declared where an `/audit-log/{id}` cannot shadow it, and the export audits
itself without appearing in its own file.
"""

import csv
import io
import json
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.api.v1.endpoints.admin import router as admin_router
from app.core.constants import AccountStatus, AuditAction, UserRole
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.user import User
from app.services import audit_csv, audit_service

LIST = "/api/v1/admin/audit-log"
EXPORT = "/api/v1/admin/audit-log/export"

#: The frontend's Hebrew catalogue — the source of the screen's action labels.
HE_JSON = (
    Path(__file__).resolve().parents[2] / "frontend" / "public" / "i18n" / "he.json"
)

#: The list's parameters that shape a *page*, and so have no place on a file
#: that is every matching row.
PAGE_ONLY_PARAMETERS = {"sort", "direction", "page", "page_size"}


def _make_user(db_session: Session, role: UserRole, email: str) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        account_status=AccountStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _entry(
    entry_id: str,
    *,
    actor_id: str = "actor-1",
    action: AuditAction = AuditAction.USER_APPROVED,
    entity_type: str = "User",
    entity_id: str = "entity-1",
    timestamp: datetime = datetime(2026, 9, 1, 12, 0, 0),
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """
    One audit row, not yet added to any session.

    The timestamp is stated rather than defaulted for the reason
    test_admin_audit_log.py gives: SQLite's CURRENT_TIMESTAMP is whole
    seconds, and rows sharing one would make every ordering assertion a test
    of the tiebreaker.
    """
    return AuditLog(
        id=entry_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        timestamp=timestamp,
        details=details,
        ip_address=ip_address,
    )


def _make_entry(db_session: Session, entry_id: str, **fields: Any) -> AuditLog:
    entry = _entry(entry_id, **fields)
    db_session.add(entry)
    db_session.commit()
    return entry


@pytest.fixture
def as_user():
    """Override the auth dependencies to return the given user."""

    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
def admin(db_session: Session) -> User:
    return _make_user(db_session, UserRole.ADMIN, "admin@example.com")


def _fresh(db_session: Session, user_id: str) -> User:
    """
    The user again, loaded into the session as it is now.

    The export closes its session once the file is streamed (see
    `iter_audit_log_for_export`). In the app that session is the request's own
    and nothing touches it again; here the client shares one session across
    requests, so an object loaded before an export is detached after it, and
    a second request needs the user loaded afresh — as a real one would be.
    """
    return db_session.get(User, user_id)


@pytest.fixture
def executed_sql(db_engine):
    """
    Every statement the database ran, with the execution options it ran under
    — `yield_per` and `stream_results` are visible only there.
    """
    statements: list[tuple[str, dict[str, Any]]] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append((statement, dict(context.execution_options)))

    event.listen(db_engine, "before_cursor_execute", _record)
    yield statements
    event.remove(db_engine, "before_cursor_execute", _record)


def _audit_selects(
    statements: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    return [
        (sql, options)
        for sql, options in statements
        if sql.lstrip().upper().startswith("SELECT") and "audit_logs" in sql
    ]


def _rows(response) -> list[list[str]]:
    """The file as Excel's own parser would split it — header row first."""
    assert response.status_code == 200, response.text
    text = response.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline="")))


async def _exported_ids(client, **params: Any) -> list[str]:
    return [row[0] for row in _rows(await client.get(EXPORT, params=params))[1:]]


async def _listed_ids(client, **params: Any) -> list[str]:
    """What the screen shows for the same filters, in the screen's order."""
    response = await client.get(LIST, params={**params, "page_size": 100})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_count"] <= 100, "the comparison needs the whole result"
    return [item["id"] for item in body["items"]]


def _exports_in_log(db_session: Session) -> list[AuditLog]:
    db_session.expire_all()
    return (
        db_session.query(AuditLog)
        .filter(AuditLog.action == AuditAction.DATA_EXPORTED)
        .all()
    )


# ---------------------------------------------------------------------------
# 1. Non-admin → 403
# ---------------------------------------------------------------------------


class TestPermissions:
    async def test_requires_authentication(self, client) -> None:
        response = await client.get(EXPORT)

        assert response.status_code == 401

    @pytest.mark.parametrize(
        "role", [UserRole.USER, UserRole.MODERATOR, UserRole.PROFESSIONAL]
    )
    async def test_forbidden_for_every_non_admin_role(
        self, client, db_session, as_user, role
    ) -> None:
        as_user(_make_user(db_session, role, f"{role.value}@example.com"))

        response = await client.get(EXPORT)

        assert response.status_code == 403

    @pytest.mark.parametrize(
        "role", [UserRole.USER, UserRole.MODERATOR, UserRole.PROFESSIONAL]
    )
    async def test_forbidden_whatever_the_parameters(
        self, client, db_session, as_user, role
    ) -> None:
        as_user(_make_user(db_session, role, f"{role.value}.params@example.com"))

        response = await client.get(
            EXPORT,
            params={
                "actor_id": "actor-1",
                "action_type": AuditAction.USER_APPROVED.value,
                "entity_type": "User",
                "entity_id": "entity-1",
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
            },
        )

        assert response.status_code == 403

    async def test_a_refused_export_sends_no_file_and_logs_no_export(
        self, client, db_session, as_user
    ) -> None:
        """
        The 403 comes from the router, before the endpoint body runs — so a
        moderator who tries is neither shown a row nor recorded as having
        exported anything.
        """
        _make_entry(db_session, "entry-1")
        as_user(_make_user(db_session, UserRole.MODERATOR, "mod@example.com"))

        response = await client.get(EXPORT)

        assert response.status_code == 403
        assert "entry-1" not in response.text
        assert _exports_in_log(db_session) == []

    async def test_admin_gets_the_file(self, client, db_session, as_user, admin):
        _make_entry(db_session, "entry-1")
        as_user(admin)

        assert await _exported_ids(client) == ["entry-1"]


# ---------------------------------------------------------------------------
# 2. Exactly the rows the filtered screen shows
# ---------------------------------------------------------------------------


class TestMatchesTheFilteredScreen:
    @pytest.fixture(autouse=True)
    def _log(self, db_session: Session) -> None:
        """
        TestFilters' four rows from test_admin_audit_log.py — no two filters
        select the same subset, so a union where an intersection belongs
        cannot pass — plus a fifth at 23:30 on the last day of the range, the
        row an off-by-one `date_to` drops.
        """
        db_session.add_all(
            [
                _entry(
                    "approved-by-alice",
                    actor_id="alice",
                    action=AuditAction.USER_APPROVED,
                    entity_type="User",
                    entity_id="user-1",
                    timestamp=datetime(2026, 9, 1, 8, 0, 0),
                ),
                _entry(
                    "deleted-by-alice",
                    actor_id="alice",
                    action=AuditAction.POST_DELETED,
                    entity_type="ForumPost",
                    entity_id="post-1",
                    timestamp=datetime(2026, 9, 2, 8, 0, 0),
                ),
                _entry(
                    "approved-by-bob",
                    actor_id="bob",
                    action=AuditAction.USER_APPROVED,
                    entity_type="User",
                    entity_id="user-2",
                    timestamp=datetime(2026, 9, 3, 8, 0, 0),
                ),
                _entry(
                    "deleted-by-bob",
                    actor_id="bob",
                    action=AuditAction.POST_DELETED,
                    entity_type="ForumPost",
                    entity_id="post-2",
                    timestamp=datetime(2026, 9, 4, 8, 0, 0),
                ),
                _entry(
                    "late-on-the-third",
                    actor_id="carol",
                    action=AuditAction.REPORT_DECIDED,
                    entity_type="Report",
                    entity_id="report-1",
                    timestamp=datetime(2026, 9, 3, 23, 30, 0),
                ),
            ]
        )
        db_session.commit()

    @pytest.mark.parametrize(
        "filters",
        [
            pytest.param({}, id="no filter"),
            pytest.param({"actor_id": "alice"}, id="actor"),
            pytest.param({"action_type": "post_deleted"}, id="action"),
            pytest.param({"entity_type": "User"}, id="entity type"),
            pytest.param({"entity_id": "post-2"}, id="entity id"),
            pytest.param(
                {"date_from": "2026-09-02", "date_to": "2026-09-03"},
                id="date range, both ends inclusive",
            ),
            pytest.param({"date_to": "2026-09-03"}, id="date_to alone"),
            pytest.param(
                {"actor_id": "alice", "action_type": "user_approved"},
                id="two filters intersect",
            ),
            pytest.param(
                {"entity_type": "User", "date_from": "2026-09-02"},
                id="a filter and a date",
            ),
            pytest.param(
                {
                    "actor_id": "bob",
                    "action_type": "post_deleted",
                    "entity_type": "ForumPost",
                    "entity_id": "post-2",
                    "date_from": "2026-09-04",
                    "date_to": "2026-09-04",
                },
                id="every filter at once",
            ),
            pytest.param(
                {"actor_id": "alice", "entity_id": "post-2"}, id="contradictory"
            ),
        ],
    )
    async def test_the_file_is_the_screen(
        self, client, as_user, admin, filters
    ) -> None:
        """Same rows, same order, for every shape of filter the screen offers."""
        as_user(admin)

        listed = await _listed_ids(client, **filters)
        exported = await _exported_ids(client, **filters)

        assert exported == listed

    async def test_two_filters_are_the_intersection_not_the_union(
        self, client, as_user, admin
    ) -> None:
        """The parametrised check, with the expected answer spelled out."""
        as_user(admin)

        assert await _exported_ids(
            client, actor_id="alice", action_type="user_approved"
        ) == ["approved-by-alice"]

    async def test_the_last_day_of_the_range_is_in_the_file(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        assert "late-on-the-third" in await _exported_ids(
            client, date_from="2026-09-03", date_to="2026-09-03"
        )

    async def test_newest_first_like_the_screen(self, client, as_user, admin):
        as_user(admin)

        assert await _exported_ids(client, actor_id="alice") == [
            "deleted-by-alice",
            "approved-by-alice",
        ]

    async def test_every_page_of_the_screen_not_just_the_first(
        self, client, db_session, as_user, admin
    ) -> None:
        """
        "The rows of the filtered view" means the view's whole result, not
        the 50 on screen: the pages concatenated, exactly once each.
        """
        db_session.add_all(
            _entry(
                f"bulk-{index:03d}",
                actor_id="bulk",
                timestamp=datetime(2026, 8, 1, 0, 0, 0),
            )
            for index in range(120)
        )
        db_session.commit()
        as_user(admin)

        pages: list[str] = []
        for page in (1, 2, 3):
            response = await client.get(
                LIST, params={"actor_id": "bulk", "page": page, "page_size": 50}
            )
            pages.extend(item["id"] for item in response.json()["items"])

        assert await _exported_ids(client, actor_id="bulk") == pages
        assert len(pages) == 120

    async def test_rejects_an_unknown_action_type_as_the_list_does(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        list_response = await client.get(LIST, params={"action_type": "nope"})
        export_response = await client.get(EXPORT, params={"action_type": "nope"})

        assert list_response.status_code == export_response.status_code == 422

    async def test_ignores_the_paging_parameters_and_exports_everything(
        self, client, as_user, admin
    ) -> None:
        """A screen on page 2 of 10-row pages still exports every match."""
        as_user(admin)

        exported = await _exported_ids(client, page=2, page_size=1)

        assert len(exported) == 5


class TestSameContractAsTheList:
    """ABF-161: "שיתוף אותם פרמטרי פילטר בדיוק"."""

    @staticmethod
    def _parameters(path: str) -> dict[str, dict[str, Any]]:
        operation = app.openapi()["paths"][path]["get"]
        return {param["name"]: param for param in operation.get("parameters", [])}

    def test_the_export_takes_exactly_the_lists_filters(self) -> None:
        """
        Compared through the OpenAPI schema, so a filter added to the list and
        forgotten on the export — or declared with a different type — fails.
        """
        list_filters = {
            name: param
            for name, param in self._parameters(LIST).items()
            if name not in PAGE_ONLY_PARAMETERS
        }

        assert self._parameters(EXPORT) == list_filters

    def test_the_contracts_six_filters(self) -> None:
        assert set(self._parameters(EXPORT)) == {
            "actor_id",
            "action_type",
            "entity_type",
            "entity_id",
            "date_from",
            "date_to",
        }

    def test_declared_before_any_parametrised_audit_log_route(self) -> None:
        """
        FastAPI matches in declaration order. ABF-153 adds
        `GET /audit-log/{entry_id}`; declared above this route, it would
        answer `/audit-log/export` as an entry called "export" and 404.

        Read off the admin router itself rather than `app.routes`: matching
        order is decided inside the router the routes were declared on, and
        newer FastAPI no longer flattens included routers into `app.routes`.
        """
        paths = [getattr(route, "path", "") for route in admin_router.routes]
        export_at = paths.index("/admin/audit-log/export")
        parametrised = [
            index
            for index, path in enumerate(paths)
            if path.startswith("/admin/audit-log/{")
        ]

        assert all(export_at < index for index in parametrised)


# ---------------------------------------------------------------------------
# 3. A file Excel opens cleanly
# ---------------------------------------------------------------------------


class TestTheFile:
    async def test_is_csv_in_utf8(self, client, db_session, as_user, admin):
        _make_entry(db_session, "entry-1")
        as_user(admin)

        response = await client.get(EXPORT)

        assert response.headers["content-type"] == "text/csv; charset=utf-8"

    async def test_starts_with_the_utf8_bom(self, client, db_session, as_user, admin):
        """The three bytes that stop Excel reading Hebrew as Windows-1255."""
        _make_entry(db_session, "entry-1")
        as_user(admin)

        response = await client.get(EXPORT)

        assert response.content.startswith(b"\xef\xbb\xbf")
        assert not response.content[3:].startswith(b"\xef\xbb\xbf")

    async def test_headers_are_hebrew(self, client, as_user, admin) -> None:
        as_user(admin)

        header = _rows(await client.get(EXPORT))[0]

        assert header == [
            "מזהה רשומה",
            "מזהה מבצע/ת הפעולה",
            "פעולה",
            "קוד פעולה",
            "תאריך ושעה (UTC)",
            "סוג ישות",
            "מזהה ישות",
            "פרטים",
        ]

    async def test_headers_stay_hebrew_for_an_admin_browsing_in_english(
        self, client, as_user, admin
    ) -> None:
        """The file is for its Hebrew-reading recipient, not the clicker."""
        as_user(admin)

        response = await client.get(EXPORT, headers={"Accept-Language": "en"})

        assert _rows(response)[0] == list(audit_csv.COLUMNS)

    async def test_downloads_as_a_dated_attachment(self, client, as_user, admin):
        as_user(admin)

        response = await client.get(EXPORT)

        assert re.fullmatch(
            r'attachment; filename="audit-log-\d{4}-\d{2}-\d{2}\.csv"',
            response.headers["content-disposition"],
        )

    async def test_is_not_cached(self, client, as_user, admin) -> None:
        as_user(admin)

        response = await client.get(EXPORT)

        assert response.headers["cache-control"] == "no-store"

    async def test_one_row_reads_as_the_screen_does(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_entry(
            db_session,
            "entry-1",
            actor_id="admin-0001",
            action=AuditAction.USER_SUSPENDED,
            entity_type="User",
            entity_id="user-0009",
            timestamp=datetime(2026, 9, 1, 15, 4, 5),
            details={"reason": "הפרת תקנון", "hours": 48},
        )
        as_user(admin)

        row = _rows(await client.get(EXPORT))[1]

        assert row == [
            "entry-1",
            "admin-0001",
            "השעיית משתמש/ת",
            "user_suspended",
            "2026-09-01 15:04:05",
            "User",
            "user-0009",
            '{"reason": "הפרת תקנון", "hours": 48}',
        ]

    async def test_details_keep_their_hebrew_readable(
        self, client, db_session, as_user, admin
    ) -> None:
        """JSON, but not `\\u05d4\\u05e4...` — a lawyer has to read it."""
        _make_entry(db_session, "entry-1", details={"reason": "הפרת תקנון"})
        as_user(admin)

        details = _rows(await client.get(EXPORT))[1][7]

        assert "\\u" not in details
        assert json.loads(details) == {"reason": "הפרת תקנון"}

    async def test_no_details_is_an_empty_cell(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_entry(db_session, "entry-1", details=None)
        as_user(admin)

        assert _rows(await client.get(EXPORT))[1][7] == ""

    async def test_never_contains_the_ip_address(
        self, client, db_session, as_user, admin
    ) -> None:
        """Asserted on a row that has one: a NULL column would prove nothing."""
        _make_entry(db_session, "entry-1", ip_address="203.0.113.77")
        as_user(admin)

        response = await client.get(EXPORT)

        assert "203.0.113.77" not in response.content.decode("utf-8-sig")
        assert not any("IP" in header.upper() for header in _rows(response)[0])

    async def test_a_filter_matching_nothing_is_a_valid_empty_file(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_entry(db_session, "entry-1")
        as_user(admin)

        rows = _rows(await client.get(EXPORT, params={"actor_id": "nobody"}))

        assert rows == [list(audit_csv.COLUMNS)]

    async def test_lines_end_in_crlf(self, client, db_session, as_user, admin):
        _make_entry(db_session, "entry-1")
        as_user(admin)

        text = (await client.get(EXPORT)).content.decode("utf-8-sig")

        assert text.count("\r\n") == 2
        assert "\n" not in text.replace("\r\n", "")

    async def test_commas_quotes_and_newlines_survive_the_round_trip(
        self, client, db_session, as_user, admin
    ) -> None:
        details = {"reason": 'line one,\nline "two"'}
        _make_entry(db_session, "entry-1", entity_type="A, B", details=details)
        as_user(admin)

        row = _rows(await client.get(EXPORT))[1]

        assert row[5] == "A, B"
        assert json.loads(row[7]) == details

    @pytest.mark.parametrize(
        "stored",
        [
            '=HYPERLINK("http://evil.example","open")',
            "+SUM(1,1)",
            "-2+3",
            "@SUM(A1)",
            "\t=1+1",
            "\r=1+1",
        ],
    )
    async def test_a_cell_excel_would_run_is_written_as_text(
        self, client, db_session, as_user, admin, stored
    ) -> None:
        _make_entry(db_session, "entry-1", entity_id=stored)
        as_user(admin)

        assert _rows(await client.get(EXPORT))[1][6] == f"'{stored}"

    async def test_an_ordinary_cell_is_written_exactly_as_stored(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_entry(db_session, "entry-1", entity_id="user-0009=ok")
        as_user(admin)

        assert _rows(await client.get(EXPORT))[1][6] == "user-0009=ok"


class TestActionLabels:
    """The `פעולה` column says what the screen says."""

    def test_every_action_has_a_hebrew_label(self) -> None:
        assert set(audit_csv.ACTION_LABELS) == set(AuditAction)

    def test_the_labels_are_the_screens_own_wording(self) -> None:
        """
        Against he.json's `constants.audit_action.*`: one wording edited and
        not the other would give the lawyer a file that names an action
        differently from the screenshot beside it.
        """
        catalogue = json.loads(HE_JSON.read_text(encoding="utf-8"))
        screen = catalogue["constants"]["audit_action"]

        assert {
            action.value: label for action, label in audit_csv.ACTION_LABELS.items()
        } == screen


# ---------------------------------------------------------------------------
# The export audits itself
# ---------------------------------------------------------------------------


class TestTheExportIsAudited:
    async def test_records_who_exported_and_under_which_filters(
        self, client, db_session, as_user, admin
    ) -> None:
        admin_id = admin.id
        as_user(admin)

        await client.get(
            EXPORT,
            params={
                "actor_id": "alice",
                "action_type": "user_approved",
                "date_from": "2026-09-01",
            },
        )

        [export] = _exports_in_log(db_session)
        assert export.actor_id == admin_id
        assert export.entity_type == "AuditLog"
        assert export.entity_id == admin_id
        assert export.details == {
            "format": "csv",
            "filters": {
                "actor_id": "alice",
                "action_type": "user_approved",
                "date_from": "2026-09-01",
            },
        }

    async def test_the_export_is_not_in_its_own_file(
        self, client, db_session, as_user, admin
    ) -> None:
        """The screen showed one row; the file holds that one row, not two."""
        _make_entry(db_session, "entry-1")
        as_user(admin)

        assert await _exported_ids(client) == ["entry-1"]
        assert len(_exports_in_log(db_session)) == 1

    async def test_an_earlier_export_is_in_the_next_file(
        self, client, db_session, as_user, admin
    ) -> None:
        """Excluded from its own file only — by then it is on the screen."""
        admin_id = admin.id
        as_user(admin)

        await client.get(EXPORT)
        [first] = _exports_in_log(db_session)
        as_user(_fresh(db_session, admin_id))

        assert await _exported_ids(client) == [first.id]


# ---------------------------------------------------------------------------
# 4. No full-table fetch
# ---------------------------------------------------------------------------


class TestTheQueryIsBoundedInTheDatabase:
    @pytest.fixture(autouse=True)
    def _log(self, db_session: Session) -> None:
        db_session.add_all(
            _entry(
                f"entry-{index:04d}",
                actor_id="actor-1" if index % 2 else "actor-2",
                timestamp=datetime(2026, 9, 1, 0, 0, 0),
            )
            for index in range(200)
        )
        db_session.commit()

    @staticmethod
    def _export_select(executed_sql) -> tuple[str, dict[str, Any]]:
        """The one SELECT that reads the rows — not the export's own INSERT."""
        selects = [
            (sql, options)
            for sql, options in _audit_selects(executed_sql)
            if "ORDER BY" in sql.upper()
        ]
        assert len(selects) == 1, selects
        return selects[0]

    async def test_the_filters_are_applied_by_the_database(
        self, client, as_user, admin, executed_sql
    ) -> None:
        """
        The SQL itself narrows the rows — a handler that read the table and
        filtered in Python would return the same file and issue a SELECT with
        no actor_id condition in it.
        """
        as_user(admin)
        executed_sql.clear()

        exported = await _exported_ids(
            client, actor_id="actor-1", date_from="2026-09-01"
        )

        sql, _ = self._export_select(executed_sql)
        where = sql.upper().split("WHERE", 1)[1]
        assert "AUDIT_LOGS.ACTOR_ID" in where
        assert "AUDIT_LOGS.TIMESTAMP" in where
        assert len(exported) == 100

    async def test_rows_are_read_a_batch_at_a_time(
        self, client, as_user, admin, executed_sql
    ) -> None:
        """
        `yield_per` is what makes the read incremental: SQLAlchemy fetches
        EXPORT_BATCH_SIZE rows at a time and asks the driver to stream
        (`stream_results`) — a server-side cursor on Postgres, see below.
        """
        as_user(admin)
        executed_sql.clear()

        await client.get(EXPORT)

        _, options = self._export_select(executed_sql)
        assert options.get("yield_per") == audit_service.EXPORT_BATCH_SIZE
        assert options.get("stream_results") is True

    async def test_no_limit_cuts_the_file_short(
        self, client, as_user, admin, executed_sql
    ) -> None:
        """Bounded by its filters, not by a page: all 200 rows arrive."""
        as_user(admin)
        executed_sql.clear()

        exported = await _exported_ids(client)

        sql, _ = self._export_select(executed_sql)
        assert "LIMIT" not in sql.upper()
        assert len(exported) == 200


class TestStreaming:
    """The pieces between the cursor and the socket hold one batch, no more."""

    @staticmethod
    def _counted(consumed: list[int], count: int) -> Iterator[AuditLog]:
        for index in range(count):
            consumed.append(index)
            yield _entry(f"entry-{index}")

    def test_the_first_chunk_leaves_before_the_next_batch_is_read(self) -> None:
        consumed: list[int] = []
        chunks = audit_csv.csv_chunks(self._counted(consumed, 5), batch_size=2)

        first = next(chunks)

        assert consumed == [0, 1]
        assert first.startswith(audit_csv.UTF8_BOM)
        assert first.count("\r\n") == 3  # the header and two rows

    def test_the_chunks_together_are_the_whole_file(self) -> None:
        chunks = list(audit_csv.csv_chunks(self._counted([], 5), batch_size=2))

        rows = list(csv.reader(io.StringIO("".join(chunks)[1:], newline="")))
        assert len(chunks) == 3
        assert [row[0] for row in rows[1:]] == [f"entry-{i}" for i in range(5)]

    def test_a_last_batch_that_closes_exactly_sends_no_empty_chunk(self) -> None:
        chunks = list(audit_csv.csv_chunks(self._counted([], 4), batch_size=2))

        assert len(chunks) == 2
        assert all(chunks)

    def test_the_session_is_closed_once_the_rows_are_read(
        self, db_session: Session
    ) -> None:
        _make_entry(db_session, "entry-1")

        rows = list(audit_service.iter_audit_log_for_export(db_session))

        assert [row.id for row in rows] == ["entry-1"]
        assert not db_session.in_transaction()

    def test_the_session_is_closed_when_the_download_is_abandoned(
        self, db_session: Session
    ) -> None:
        """The client hanging up half-way still gives the connection back."""
        _make_entry(db_session, "entry-1")
        _make_entry(db_session, "entry-2")
        rows = audit_service.iter_audit_log_for_export(db_session)

        next(rows)
        assert db_session.in_transaction()
        rows.close()

        assert not db_session.in_transaction()


class TestOnPostgres:
    """Skipped without TEST_POSTGRES_URL; CI sets it (see conftest.py)."""

    def test_reads_through_a_server_side_cursor(self, pg_engine, pg_session):
        """
        On psycopg2 a server-side cursor is a *named* one, so the cursor's
        name is the proof: Postgres holds the result and hands it over a
        batch at a time, and the process never has the table in memory.
        """
        pg_session.add_all(
            _entry(f"entry-{index:04d}", actor_id="actor-1") for index in range(3)
        )
        pg_session.commit()
        cursor_names: list[str | None] = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                cursor_names.append(getattr(cursor, "name", None))

        event.listen(pg_engine, "before_cursor_execute", _record)
        try:
            rows = list(
                audit_service.iter_audit_log_for_export(pg_session, actor_id="actor-1")
            )
        finally:
            event.remove(pg_engine, "before_cursor_execute", _record)

        assert len(rows) == 3
        assert cursor_names and all(cursor_names)

    def test_filters_and_order_match_the_list_on_postgres(self, pg_session):
        pg_session.add_all(
            [
                _entry("a", actor_id="x", timestamp=datetime(2026, 9, 1, 8)),
                _entry("b", actor_id="x", timestamp=datetime(2026, 9, 2, 8)),
                _entry("c", actor_id="y", timestamp=datetime(2026, 9, 3, 8)),
            ]
        )
        pg_session.commit()

        listed, _ = audit_service.get_audit_log(pg_session, actor_id="x")
        exported = list(
            audit_service.iter_audit_log_for_export(pg_session, actor_id="x")
        )

        assert [row.id for row in exported] == [row.id for row in listed] == ["b", "a"]
