"""
GET /api/v1/admin/audit-log — the audit log as an admin actually reads it
(ABF-152): filtered, sorted, paginated, and bounded in the database.

Four things this file is built around, in the order they can bite:

1. **Who may read it at all.** §9.3 gives the audit log to ADMIN and nobody
   else, so the permission matrix covers all four roles rather than the one
   that is easy to think of. A moderator is the dangerous case: they hold the
   next-highest role, they are already trusted with reported content, and
   every other moderation route lets them in.
2. **`ip_address` never leaves the server.** The column exists and is
   populated; the decision on this ticket is that no screen and no parameter
   exposes it. Asserted on a row that *has* one, because a test that passes
   against a NULL column proves nothing.
3. **The intersection of filters.** Each filter alone is easy; the bug is two
   filters that each match a row the other does not, and a response that
   contains the union.
4. **The query is bounded in SQL.** The acceptance criterion is not "the
   response holds 50 rows" — that is also true of fetching ten thousand and
   slicing in Python. So the SQL itself is captured and inspected: the page
   query carries a LIMIT, and nothing ever selects the table unbounded.
"""

from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.constants import AccountStatus, AuditAction, UserRole
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.user import User

BASE = "/api/v1/admin/audit-log"


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


def _make_entry(
    db_session: Session,
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
    One audit row, with the timestamp supplied rather than defaulted.

    `AuditLog.timestamp` has a `server_default` of CURRENT_TIMESTAMP, which on
    SQLite is whole seconds — rows written in a loop would share one to the
    second, and every ordering assertion below would be testing the tiebreaker
    instead of the column it names. Stating the instant is what lets a test
    about sorting be about sorting.
    """
    entry = AuditLog(
        id=entry_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        timestamp=timestamp,
        details=details,
        ip_address=ip_address,
    )
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


@pytest.fixture
def executed_sql(db_engine):
    """
    Every statement the database actually ran, as the driver received it.

    The point of this ticket that cannot be checked from the response body: a
    handler that fetches the whole table and slices it in Python returns
    exactly the same JSON as one that pages in SQL, and differs only in what
    it does to a table with seven years of rows in it.
    """
    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db_engine, "before_cursor_execute", _record)
    yield statements
    event.remove(db_engine, "before_cursor_execute", _record)


def _audit_selects(statements: list[str]) -> list[str]:
    """The SELECTs that read audit_logs — the count query included."""
    return [
        sql
        for sql in statements
        if sql.lstrip().upper().startswith("SELECT") and "audit_logs" in sql
    ]


def _is_bounded(sql: str) -> bool:
    """
    Whether one SELECT over audit_logs can be trusted not to stream the table.

    `COUNT(*)` is a bounded aggregate the database answers by itself, so it is
    allowed to have no LIMIT. A plain `SELECT ... FROM audit_logs` with
    neither is the whole table coming back over the wire, which is the thing
    being forbidden.
    """
    return "LIMIT" in sql.upper() or "count(" in sql.lower()


class TestPermissions:
    """
    The 4-role matrix. §9.3 gives the audit log to ADMIN alone, and the
    acceptance criterion is explicit that the 403 does not depend on what was
    asked for — so the three refused roles are also tried with a full set of
    parameters, not just with a bare URL.
    """

    async def test_requires_authentication(self, client) -> None:
        response = await client.get(BASE)

        assert response.status_code == 401

    @pytest.mark.parametrize(
        "role",
        [UserRole.USER, UserRole.MODERATOR, UserRole.PROFESSIONAL],
    )
    async def test_forbidden_for_every_non_admin_role(
        self, client, db_session, as_user, role
    ) -> None:
        as_user(_make_user(db_session, role, f"{role.value}@example.com"))

        response = await client.get(BASE)

        assert response.status_code == 403

    @pytest.mark.parametrize(
        "role",
        [UserRole.USER, UserRole.MODERATOR, UserRole.PROFESSIONAL],
    )
    async def test_forbidden_whatever_the_parameters(
        self, client, db_session, as_user, role
    ) -> None:
        as_user(_make_user(db_session, role, f"{role.value}.params@example.com"))

        response = await client.get(
            BASE,
            params={
                "actor_id": "actor-1",
                "action_type": AuditAction.USER_APPROVED.value,
                "entity_type": "User",
                "entity_id": "entity-1",
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
                "sort": "timestamp",
                "direction": "asc",
                "page": 1,
                "page_size": 10,
            },
        )

        assert response.status_code == 403

    async def test_admin_reads_real_rows_from_the_database(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_entry(db_session, "entry-1")
        as_user(admin)

        response = await client.get(BASE)

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == ["entry-1"]


class TestResponseShape:
    async def test_carries_exactly_the_contract_fields(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_entry(
            db_session,
            "entry-1",
            actor_id="admin-7",
            action=AuditAction.USER_SUSPENDED,
            entity_type="User",
            entity_id="user-42",
            details={"hours": 24},
        )
        as_user(admin)

        response = await client.get(BASE)

        [item] = response.json()["items"]
        assert set(item) == {
            "id",
            "actor_id",
            "action_type",
            "entity_type",
            "entity_id",
            "timestamp",
            "details",
        }
        assert item["id"] == "entry-1"
        assert item["actor_id"] == "admin-7"
        assert item["action_type"] == AuditAction.USER_SUSPENDED.value
        assert item["entity_type"] == "User"
        assert item["entity_id"] == "user-42"
        assert item["details"] == {"hours": 24}

    async def test_names_the_column_action_type_not_action(
        self, client, db_session, as_user, admin
    ) -> None:
        """The contract froze `action_type`; the column is called `action`."""
        _make_entry(db_session, "entry-1", action=AuditAction.POST_DELETED)
        as_user(admin)

        response = await client.get(BASE)

        [item] = response.json()["items"]
        assert item["action_type"] == AuditAction.POST_DELETED.value
        assert "action" not in item

    async def test_never_returns_the_ip_address(
        self, client, db_session, as_user, admin
    ) -> None:
        """
        The row has an IP. The response does not, anywhere in it — checked
        against the serialized body rather than the parsed item, so a value
        that reappears nested inside `details` is caught too.
        """
        _make_entry(db_session, "entry-1", ip_address="203.0.113.7")
        as_user(admin)

        response = await client.get(BASE)

        assert "203.0.113.7" not in response.text
        assert "ip_address" not in response.text

    async def test_details_may_be_absent(
        self, client, db_session, as_user, admin
    ) -> None:
        """Most entries carry none; null is a value, not a missing field."""
        _make_entry(db_session, "entry-1", details=None)
        as_user(admin)

        response = await client.get(BASE)

        [item] = response.json()["items"]
        assert item["details"] is None

    async def test_reports_the_page_it_answered_with(
        self, client, db_session, as_user, admin
    ) -> None:
        for index in range(3):
            _make_entry(db_session, f"entry-{index}")
        as_user(admin)

        response = await client.get(BASE, params={"page": 2, "page_size": 2})

        body = response.json()
        assert body["page"] == 2
        assert body["page_size"] == 2
        assert body["total_count"] == 3

    async def test_empty_log_is_an_empty_page_not_an_error(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        response = await client.get(BASE)

        assert response.status_code == 200
        assert response.json() == {
            "items": [],
            "total_count": 0,
            "page": 1,
            "page_size": 50,
        }

    async def test_a_filter_that_matches_nothing_is_an_empty_page(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_entry(db_session, "entry-1", actor_id="actor-1")
        as_user(admin)

        response = await client.get(BASE, params={"actor_id": "nobody"})

        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total_count"] == 0


class TestFilters:
    @pytest.fixture(autouse=True)
    def _log(self, db_session: Session) -> None:
        """
        Four rows that differ along every filterable axis, arranged so that no
        two filters select the same subset — which is what makes a combination
        test able to fail.
        """
        _make_entry(
            db_session,
            "approved-by-alice",
            actor_id="alice",
            action=AuditAction.USER_APPROVED,
            entity_type="User",
            entity_id="user-1",
            timestamp=datetime(2026, 9, 1, 8, 0, 0),
        )
        _make_entry(
            db_session,
            "deleted-by-alice",
            actor_id="alice",
            action=AuditAction.POST_DELETED,
            entity_type="ForumPost",
            entity_id="post-1",
            timestamp=datetime(2026, 9, 2, 8, 0, 0),
        )
        _make_entry(
            db_session,
            "approved-by-bob",
            actor_id="bob",
            action=AuditAction.USER_APPROVED,
            entity_type="User",
            entity_id="user-2",
            timestamp=datetime(2026, 9, 3, 8, 0, 0),
        )
        _make_entry(
            db_session,
            "deleted-by-bob",
            actor_id="bob",
            action=AuditAction.POST_DELETED,
            entity_type="ForumPost",
            entity_id="post-2",
            timestamp=datetime(2026, 9, 4, 8, 0, 0),
        )

    @staticmethod
    async def _ids(client, **params: Any) -> set[str]:
        response = await client.get(BASE, params=params)
        assert response.status_code == 200, response.text
        return {item["id"] for item in response.json()["items"]}

    async def test_no_filter_returns_the_whole_log(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        assert await self._ids(client) == {
            "approved-by-alice",
            "deleted-by-alice",
            "approved-by-bob",
            "deleted-by-bob",
        }

    async def test_actor_id(self, client, as_user, admin) -> None:
        as_user(admin)

        assert await self._ids(client, actor_id="alice") == {
            "approved-by-alice",
            "deleted-by-alice",
        }

    async def test_action_type(self, client, as_user, admin) -> None:
        as_user(admin)

        assert await self._ids(client, action_type=AuditAction.POST_DELETED.value) == {
            "deleted-by-alice",
            "deleted-by-bob",
        }

    async def test_entity_type(self, client, as_user, admin) -> None:
        as_user(admin)

        assert await self._ids(client, entity_type="ForumPost") == {
            "deleted-by-alice",
            "deleted-by-bob",
        }

    async def test_entity_id(self, client, as_user, admin) -> None:
        as_user(admin)

        assert await self._ids(client, entity_id="post-2") == {"deleted-by-bob"}

    async def test_date_range_includes_both_end_days(
        self, client, as_user, admin
    ) -> None:
        """
        A range stated as two days holds everything written on either of them.
        `timestamp <= date_to` — the obvious spelling — would place the upper
        bound at midnight *opening* the 3rd and silently drop
        `approved-by-bob`, which was written eight hours into it.
        """
        as_user(admin)

        assert await self._ids(
            client, date_from="2026-09-02", date_to="2026-09-03"
        ) == {"deleted-by-alice", "approved-by-bob"}

    async def test_a_single_day_range_is_that_day(self, client, as_user, admin) -> None:
        as_user(admin)

        assert await self._ids(
            client, date_from="2026-09-02", date_to="2026-09-02"
        ) == {"deleted-by-alice"}

    async def test_date_from_alone_is_an_open_ended_range(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        assert await self._ids(client, date_from="2026-09-03") == {
            "approved-by-bob",
            "deleted-by-bob",
        }

    async def test_date_to_alone_is_an_open_ended_range(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        assert await self._ids(client, date_to="2026-09-02") == {
            "approved-by-alice",
            "deleted-by-alice",
        }

    async def test_two_filters_intersect_rather_than_union(
        self, client, as_user, admin
    ) -> None:
        """
        `actor_id=alice` alone matches two rows and `action_type=post_deleted`
        alone matches two others; exactly one row satisfies both. A handler
        that ORs its filters returns three here.
        """
        as_user(admin)

        assert await self._ids(
            client, actor_id="alice", action_type=AuditAction.POST_DELETED.value
        ) == {"deleted-by-alice"}

    async def test_a_filter_and_a_date_range_intersect_too(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        assert await self._ids(
            client,
            action_type=AuditAction.USER_APPROVED.value,
            date_from="2026-09-02",
        ) == {"approved-by-bob"}

    async def test_every_filter_at_once(self, client, as_user, admin) -> None:
        as_user(admin)

        assert await self._ids(
            client,
            actor_id="bob",
            action_type=AuditAction.POST_DELETED.value,
            entity_type="ForumPost",
            entity_id="post-2",
            date_from="2026-09-04",
            date_to="2026-09-04",
        ) == {"deleted-by-bob"}

    async def test_combined_filters_that_contradict_return_nothing(
        self, client, as_user, admin
    ) -> None:
        """Alice never deleted post-2; asking for both is an empty page."""
        as_user(admin)

        assert await self._ids(client, actor_id="alice", entity_id="post-2") == set()

    async def test_total_count_follows_the_filters(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        response = await client.get(BASE, params={"actor_id": "alice"})

        assert response.json()["total_count"] == 2

    async def test_rejects_an_unknown_action_type(self, client, as_user, admin) -> None:
        as_user(admin)

        response = await client.get(BASE, params={"action_type": "not_an_action"})

        assert response.status_code == 422


class TestSorting:
    @pytest.fixture(autouse=True)
    def _log(self, db_session: Session) -> None:
        for day in (2, 1, 3):
            _make_entry(
                db_session,
                f"entry-{day}",
                timestamp=datetime(2026, 9, day, 10, 0, 0),
            )

    @staticmethod
    async def _ids_in_order(client, **params: Any) -> list[str]:
        response = await client.get(BASE, params=params)
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()["items"]]

    async def test_newest_first_by_default(self, client, as_user, admin) -> None:
        as_user(admin)

        assert await self._ids_in_order(client) == ["entry-3", "entry-2", "entry-1"]

    async def test_descending(self, client, as_user, admin) -> None:
        as_user(admin)

        assert await self._ids_in_order(client, sort="timestamp", direction="desc") == [
            "entry-3",
            "entry-2",
            "entry-1",
        ]

    async def test_ascending(self, client, as_user, admin) -> None:
        as_user(admin)

        assert await self._ids_in_order(client, sort="timestamp", direction="asc") == [
            "entry-1",
            "entry-2",
            "entry-3",
        ]

    async def test_the_two_directions_are_exact_reverses(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        ascending = await self._ids_in_order(client, direction="asc")
        descending = await self._ids_in_order(client, direction="desc")

        assert ascending == list(reversed(descending))

    async def test_sorting_survives_a_tie_on_the_timestamp(
        self, client, db_session, as_user, admin
    ) -> None:
        """
        One admin action writes several rows in one transaction, and they
        share a timestamp exactly. Without the id in the ORDER BY the order
        within the tie is whatever the database felt like, so `asc` and `desc`
        stop being reverses of each other and a page boundary falling inside
        the tie repeats a row.
        """
        tied = datetime(2026, 9, 9, 10, 0, 0)
        for suffix in ("a", "b", "c"):
            _make_entry(db_session, f"tied-{suffix}", timestamp=tied)
        as_user(admin)

        ascending = await self._ids_in_order(client, direction="asc")
        descending = await self._ids_in_order(client, direction="desc")

        assert ascending == list(reversed(descending))
        assert ascending[-3:] == ["tied-a", "tied-b", "tied-c"]

    async def test_rejects_an_unknown_sort_column(self, client, as_user, admin) -> None:
        """
        `sort` reaches `order_by()`. An unknown value has to be refused by the
        contract rather than passed through to SQLAlchemy — `ip_address` is a
        real column on this table.
        """
        as_user(admin)

        response = await client.get(BASE, params={"sort": "ip_address"})

        assert response.status_code == 422

    async def test_rejects_an_unknown_direction(self, client, as_user, admin) -> None:
        as_user(admin)

        response = await client.get(BASE, params={"direction": "sideways"})

        assert response.status_code == 422


class TestPagination:
    @pytest.fixture(autouse=True)
    def _log(self, db_session: Session) -> None:
        for day in range(1, 6):
            _make_entry(
                db_session,
                f"entry-{day}",
                timestamp=datetime(2026, 9, day, 10, 0, 0),
            )

    async def test_page_two_holds_different_rows_from_page_one(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        first = await client.get(BASE, params={"page": 1, "page_size": 2})
        second = await client.get(BASE, params={"page": 2, "page_size": 2})

        first_ids = [item["id"] for item in first.json()["items"]]
        second_ids = [item["id"] for item in second.json()["items"]]

        assert first_ids == ["entry-5", "entry-4"]
        assert second_ids == ["entry-3", "entry-2"]
        assert set(first_ids).isdisjoint(second_ids)

    async def test_the_pages_together_are_the_whole_log_exactly_once(
        self, client, as_user, admin
    ) -> None:
        """No row repeated across a page boundary, and none skipped."""
        as_user(admin)

        collected: list[str] = []
        for page in (1, 2, 3):
            response = await client.get(BASE, params={"page": page, "page_size": 2})
            collected += [item["id"] for item in response.json()["items"]]

        assert collected == ["entry-5", "entry-4", "entry-3", "entry-2", "entry-1"]

    async def test_total_count_is_the_whole_log_not_the_page(
        self, client, as_user, admin
    ) -> None:
        """
        The count that tells the pager there is a page 2. `len(items)` would
        report 2 here and leave the reader on "page 1 of 1".
        """
        as_user(admin)

        response = await client.get(BASE, params={"page": 1, "page_size": 2})

        assert len(response.json()["items"]) == 2
        assert response.json()["total_count"] == 5

    async def test_total_count_is_the_same_on_every_page(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        counts = []
        for page in (1, 2, 3):
            response = await client.get(BASE, params={"page": page, "page_size": 2})
            counts.append(response.json()["total_count"])

        assert counts == [5, 5, 5]

    async def test_a_page_past_the_end_is_empty_with_the_count_intact(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        response = await client.get(BASE, params={"page": 99, "page_size": 2})

        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total_count"] == 5

    async def test_pagination_applies_after_the_filters(
        self, client, db_session, as_user, admin
    ) -> None:
        _make_entry(
            db_session,
            "by-someone-else",
            actor_id="bob",
            timestamp=datetime(2026, 9, 6, 10, 0, 0),
        )
        as_user(admin)

        response = await client.get(
            BASE, params={"actor_id": "actor-1", "page": 1, "page_size": 2}
        )

        body = response.json()
        assert [item["id"] for item in body["items"]] == ["entry-5", "entry-4"]
        assert body["total_count"] == 5

    @pytest.mark.parametrize("page_size", [0, 101])
    async def test_rejects_a_page_size_outside_the_allowed_range(
        self, client, as_user, admin, page_size
    ) -> None:
        """
        The cap is what stops "give me the whole table" being a legal request.
        Zero is refused at the other end: it makes every page empty while
        `total_count` insists there is more.
        """
        as_user(admin)

        response = await client.get(BASE, params={"page_size": page_size})

        assert response.status_code == 422

    async def test_rejects_page_zero(self, client, as_user, admin) -> None:
        as_user(admin)

        response = await client.get(BASE, params={"page": 0})

        assert response.status_code == 422


class TestTheQueryIsBoundedInTheDatabase:
    """
    The acceptance criterion the response body cannot show: "the query itself
    is limited — nothing fetches the whole table at any stage".
    """

    @pytest.fixture(autouse=True)
    def _log(self, db_session: Session) -> None:
        db_session.add_all(
            AuditLog(
                id=f"entry-{index:04d}",
                actor_id="actor-1" if index % 2 else "actor-2",
                action=AuditAction.USER_APPROVED,
                entity_type="User",
                entity_id=f"user-{index}",
                timestamp=datetime(2026, 9, 1, 0, 0, 0),
            )
            for index in range(200)
        )
        db_session.commit()

    async def test_the_page_query_carries_a_limit(
        self, client, as_user, admin, executed_sql
    ) -> None:
        as_user(admin)
        executed_sql.clear()

        await client.get(BASE, params={"page_size": 10})

        page_queries = [
            sql for sql in _audit_selects(executed_sql) if "count(" not in sql.lower()
        ]
        assert page_queries, "no SELECT against audit_logs was issued"
        for sql in page_queries:
            assert "LIMIT" in sql.upper(), sql

    async def test_nothing_selects_the_table_unbounded(
        self, client, as_user, admin, executed_sql
    ) -> None:
        as_user(admin)
        executed_sql.clear()

        await client.get(BASE, params={"page_size": 10})

        for sql in _audit_selects(executed_sql):
            assert _is_bounded(sql), f"unbounded SELECT over audit_logs: {sql}"

    async def test_returns_only_the_page_asked_for_out_of_two_hundred_rows(
        self, client, as_user, admin
    ) -> None:
        as_user(admin)

        response = await client.get(BASE, params={"page_size": 10})

        assert len(response.json()["items"]) == 10
        assert response.json()["total_count"] == 200

    async def test_the_count_is_its_own_query_not_the_page_counted(
        self, client, as_user, admin, executed_sql
    ) -> None:
        """
        `total_count` has to be able to disagree with `len(items)` for it to be
        worth having, and it has to come from SQL for it to be right.
        """
        as_user(admin)
        executed_sql.clear()

        response = await client.get(BASE, params={"page_size": 10})

        assert any("count(" in sql.lower() for sql in _audit_selects(executed_sql))
        assert response.json()["total_count"] != len(response.json()["items"])

    async def test_a_filtered_page_deep_in_the_log_is_bounded_too(
        self, client, as_user, admin, executed_sql
    ) -> None:
        as_user(admin)
        executed_sql.clear()

        response = await client.get(
            BASE, params={"actor_id": "actor-1", "page": 3, "page_size": 10}
        )

        for sql in _audit_selects(executed_sql):
            assert _is_bounded(sql), f"unbounded SELECT over audit_logs: {sql}"
        assert len(response.json()["items"]) == 10
        assert response.json()["total_count"] == 100
