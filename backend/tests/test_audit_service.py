"""
`audit_service.get_audit_log()` on its own terms (ABF-152).

`test_admin_audit_log.py` covers the same behaviour through HTTP, which is
where the filters and the permission matrix belong. This file is about the
*service* contract, because Task 2 (the single-entry view) calls this function
directly and gets none of FastAPI's help:

  - it returns `(rows, total_count)` — two values, the second of which is not
    `len(rows)` and is the whole reason the signature changed;
  - its parameters are keyword-only, so a caller cannot reproduce the
    positional `get_audit_log(db, page, page_size)` the stub used to have and
    silently pass a page number as an actor id;
  - its defaults are the defaults the endpoint declares, so calling it with a
    `db` alone is a sensible newest-first first page rather than something
    only the endpoint knows how to ask for.

`log_action()` and `build_entry()` are covered where they are used — every
service that writes an audit row asserts on the row it wrote.
"""

from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from app.core.constants import AuditAction, AuditSortField, SortDirection
from app.models.audit import AuditLog
from app.services import audit_service


def _entry(
    db_session: Session,
    entry_id: str,
    *,
    actor_id: str = "actor-1",
    action: AuditAction = AuditAction.USER_APPROVED,
    entity_type: str = "User",
    entity_id: str = "entity-1",
    timestamp: datetime = datetime(2026, 9, 1, 12, 0, 0),
) -> AuditLog:
    entry = AuditLog(
        id=entry_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        timestamp=timestamp,
    )
    db_session.add(entry)
    db_session.commit()
    return entry


@pytest.fixture
def log(db_session: Session) -> None:
    """Twelve entries on twelve consecutive days, two actors, two actions."""
    for day in range(1, 13):
        _entry(
            db_session,
            f"entry-{day:02d}",
            actor_id="alice" if day % 2 else "bob",
            action=AuditAction.USER_APPROVED if day % 3 else AuditAction.POST_DELETED,
            timestamp=datetime(2026, 9, day, 10, 0, 0),
        )


class TestReturnValue:
    def test_returns_the_rows_and_the_total_separately(
        self, db_session: Session, log: None
    ) -> None:
        rows, total_count = audit_service.get_audit_log(db_session, page_size=5)

        assert len(rows) == 5
        assert total_count == 12

    def test_the_total_is_not_the_length_of_the_page(
        self, db_session: Session, log: None
    ) -> None:
        """
        The whole point of the changed return value. A page of five out of
        twelve that reports five is the bug this replaced.
        """
        rows, total_count = audit_service.get_audit_log(db_session, page_size=5)

        assert total_count != len(rows)

    def test_the_total_counts_the_filtered_log_not_the_table(
        self, db_session: Session, log: None
    ) -> None:
        _, total_count = audit_service.get_audit_log(db_session, actor_id="alice")

        assert total_count == 6

    def test_returns_orm_rows_the_caller_can_read_fields_off(
        self, db_session: Session, log: None
    ) -> None:
        rows, _ = audit_service.get_audit_log(db_session, page_size=1)

        assert isinstance(rows[0], AuditLog)
        assert rows[0].id == "entry-12"

    def test_an_empty_log_is_an_empty_page_and_a_zero(
        self, db_session: Session
    ) -> None:
        rows, total_count = audit_service.get_audit_log(db_session)

        assert rows == []
        assert total_count == 0


class TestDefaults:
    def test_newest_first_fifty_at_a_time(self, db_session: Session, log: None) -> None:
        rows, _ = audit_service.get_audit_log(db_session)

        assert [row.id for row in rows][:3] == ["entry-12", "entry-11", "entry-10"]
        assert len(rows) == 12

    def test_the_page_window_is_applied_even_with_no_arguments(
        self, db_session: Session
    ) -> None:
        """
        Fifty is a default, not a suggestion: a caller who passes nothing must
        still get a bounded page, because the callers who pass nothing are
        exactly the ones not thinking about the size of this table.
        """
        for index in range(60):
            _entry(db_session, f"row-{index:03d}")

        rows, total_count = audit_service.get_audit_log(db_session)

        assert len(rows) == 50
        assert total_count == 60


class TestFilteringAndOrdering:
    def test_filters_combine_with_and(self, db_session: Session, log: None) -> None:
        rows, total_count = audit_service.get_audit_log(
            db_session,
            actor_id="alice",
            action_type=AuditAction.POST_DELETED,
        )

        assert {row.id for row in rows} == {"entry-03", "entry-09"}
        assert total_count == 2

    def test_a_date_range_is_inclusive_at_both_ends(
        self, db_session: Session, log: None
    ) -> None:
        rows, _ = audit_service.get_audit_log(
            db_session,
            date_from=date(2026, 9, 4),
            date_to=date(2026, 9, 6),
        )

        assert {row.id for row in rows} == {"entry-04", "entry-05", "entry-06"}

    def test_ascending_and_descending_are_reverses(
        self, db_session: Session, log: None
    ) -> None:
        ascending, _ = audit_service.get_audit_log(
            db_session, sort=AuditSortField.TIMESTAMP, direction=SortDirection.ASC
        )
        descending, _ = audit_service.get_audit_log(
            db_session, sort=AuditSortField.TIMESTAMP, direction=SortDirection.DESC
        )

        assert [row.id for row in ascending] == [row.id for row in descending][::-1]

    def test_paging_walks_the_log_without_repeating_or_skipping_a_row(
        self, db_session: Session, log: None
    ) -> None:
        seen: list[str] = []
        for page in (1, 2, 3, 4, 5):
            rows, _ = audit_service.get_audit_log(db_session, page=page, page_size=3)
            seen += [row.id for row in rows]

        assert seen == [f"entry-{day:02d}" for day in range(12, 0, -1)]


class TestSignature:
    def test_every_filter_is_keyword_only(self, db_session: Session, log: None) -> None:
        """
        The stub took `(db, page, page_size, action_filter, entity_type_filter)`
        positionally. Keeping that order would have made
        `get_audit_log(db, 1, 50)` keep compiling while meaning something else
        under the new signature; making everything after `db` keyword-only
        turns that into a TypeError at the call site instead.
        """
        with pytest.raises(TypeError):
            audit_service.get_audit_log(db_session, 1, 50)  # type: ignore[misc]
