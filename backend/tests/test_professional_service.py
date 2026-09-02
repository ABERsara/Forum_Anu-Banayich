"""
Unit tests for professional_service.create_query(), get_my_questions(),
get_pending_questions(), answer_query() and like_service.toggle_like().
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import event, insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Mapper, Session

from app.core.constants import (
    LikeTargetType,
    ProfessionalDomain,
    QueryStatus,
    Sector,
    UserRole,
    UserType,
)
from app.models.like import Like
from app.models.professional import ProfessionalQuery
from app.models.user import User
from app.schemas.professional import ProfessionalAnswerRequest, ProfessionalQueryCreate
from app.services import email_service, like_service, professional_service

#: Sentinel distinguishing "caller didn't pass asker_user_type/asker_sector"
#: (default to the asker's own cell) from "caller explicitly passed None"
#: (simulate a historical row with no frozen cell).
_UNSET = object()


def _make_asker(
    db_session: Session,
    email: str = "asker@example.com",
    user_type: UserType | None = UserType.WIDOW,
    sector: Sector | None = Sector.SEPHARDIC,
) -> User:
    asker = User(
        email=email,
        password_hash="hashed",
        first_name="Almana",
        last_name="Testuser",
        role=UserRole.USER,
        user_type=user_type,
        sector=sector,
    )
    db_session.add(asker)
    db_session.commit()
    return asker


def _make_professional(
    db_session: Session,
    email: str = "pro@example.com",
    domain: ProfessionalDomain = ProfessionalDomain.LAWYER,
    groups: list[str] | None = None,
    sectors: list[str] | None = None,
    is_active: bool = True,
) -> User:
    professional = User(
        email=email,
        password_hash="hashed",
        first_name="Pro",
        last_name="Fessional",
        role=UserRole.PROFESSIONAL,
        professional_domain=domain,
        professional_groups=groups if groups is not None else ["all"],
        professional_sectors=sectors if sectors is not None else ["all"],
        is_active_professional=is_active,
    )
    db_session.add(professional)
    db_session.commit()
    return professional


def _make_query(
    db_session: Session,
    asker: User,
    professional: User | None = None,
    domain: ProfessionalDomain | None = None,
    status: QueryStatus = QueryStatus.OPEN,
    content: str = "שאלה שממתינה לתשובה מאיש המקצוע",
    show_real_name: bool = False,
    is_public: bool = False,
    answer: str | None = None,
    asker_user_type: UserType | None | object = _UNSET,
    asker_sector: Sector | None | object = _UNSET,
) -> ProfessionalQuery:
    # Default to the asker's own cell, mirroring what create_query() does —
    # callers only need to override this to simulate a stale/mismatched
    # snapshot (e.g. a profile change after the question was created).
    query = ProfessionalQuery(
        asker_id=asker.id,
        professional_id=professional.id if professional is not None else None,
        domain=domain,
        content=content,
        status=status,
        show_real_name=show_real_name,
        is_public=is_public,
        answer=answer,
        asker_user_type=(
            asker.user_type if asker_user_type is _UNSET else asker_user_type
        ),
        asker_sector=asker.sector if asker_sector is _UNSET else asker_sector,
    )
    db_session.add(query)
    db_session.commit()
    return query


@pytest.fixture
def sent_answer_emails(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Capture send_answer_notification() calls instead of logging/sending them."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        email_service,
        "send_answer_notification",
        lambda asker_email, query_id: sent.append((asker_email, query_id)),
    )
    return sent


@pytest.fixture
def domain_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[list[str], str]]:
    """
    Capture send_domain_question_notification() calls — one entry per call.

    The list of calls is the assertion, not just the recipients: the fan-out
    costs one SMTP handshake per call, so "who was notified" and "in how many
    calls" are two different things worth pinning.
    """
    calls: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        email_service,
        "send_domain_question_notification",
        lambda emails, query_id: calls.append((list(emails), query_id)),
    )
    return calls


@pytest.fixture
def direct_notifications(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Capture send_direct_question_notification() calls."""
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        email_service,
        "send_direct_question_notification",
        lambda professional_email, query_id: calls.append(
            (professional_email, query_id)
        ),
    )
    return calls


class TestCreateQuery:
    def test_requires_professional_id_or_domain(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        data = ProfessionalQueryCreate(content="שאלה כללית ללא יעד" * 2)

        with pytest.raises(HTTPException) as exc_info:
            professional_service.create_query(db_session, data, asker)
        assert exc_info.value.status_code == 400

    def test_asks_specific_professional(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        data = ProfessionalQueryCreate(
            content="יש לי שאלה משפטית לגבי הירושה",
            professional_id=professional.id,
        )

        response = professional_service.create_query(db_session, data, asker)

        assert response.id is not None
        assert response.professional is not None
        assert response.professional.id == professional.id
        assert response.status == QueryStatus.OPEN
        assert response.asker_alias == "אלמנה – ספרדי"
        assert response.asker is None  # show_real_name defaults to False

        stored = db_session.get(ProfessionalQuery, response.id)
        assert stored is not None
        assert stored.asker_user_type == UserType.WIDOW
        assert stored.asker_sector == Sector.SEPHARDIC

    def test_asks_general_domain_question(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        data = ProfessionalQueryCreate(
            content="שאלה כללית לתחום הרפואה כרגע",
            domain=ProfessionalDomain.MEDICINE,
        )

        response = professional_service.create_query(db_session, data, asker)

        assert response.domain == ProfessionalDomain.MEDICINE
        assert response.professional is None

    def test_show_real_name_exposes_asker(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        data = ProfessionalQueryCreate(
            content="שאלה עם חשיפת שם מלא של השואל",
            professional_id=professional.id,
            show_real_name=True,
        )

        response = professional_service.create_query(db_session, data, asker)

        assert response.asker is not None
        assert response.asker.id == asker.id

    def test_rejects_professional_not_matching_group_or_sector(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(
            db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        professional = _make_professional(
            db_session, groups=["widower"], sectors=["hasidic"]
        )
        data = ProfessionalQueryCreate(
            content="שאלה לאיש מקצוע שלא משרת את הקבוצה שלי",
            professional_id=professional.id,
        )

        with pytest.raises(HTTPException) as exc_info:
            professional_service.create_query(db_session, data, asker)
        assert exc_info.value.status_code == 403

    def test_rejects_unknown_professional_id(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        data = ProfessionalQueryCreate(
            content="שאלה לאיש מקצוע שלא קיים כלל",
            professional_id="00000000-0000-0000-0000-000000000000",
        )

        with pytest.raises(HTTPException) as exc_info:
            professional_service.create_query(db_session, data, asker)
        assert exc_info.value.status_code == 404


class TestNewQuestionNotifications:
    """
    Who gets told about a new question, and at what cost.

    The fan-out runs inside the asker's own create_query() call, so the number
    of calls into email_service matters as much as the recipients: each call is
    its own SMTP connect, STARTTLS and login, in sequence, while she waits for
    her response.
    """

    def test_domain_question_notifies_every_professional_in_one_call(
        self,
        db_session: Session,
        domain_notifications: list[tuple[list[str], str]],
    ) -> None:
        asker = _make_asker(db_session)
        domain_pros = [
            _make_professional(
                db_session, email=f"pro{i}@example.com", domain=ProfessionalDomain.RABBI
            )
            for i in range(3)
        ]

        response = professional_service.create_query(
            db_session,
            ProfessionalQueryCreate(
                content="שאלה כללית לכל רבני העמותה",
                domain=ProfessionalDomain.RABBI,
            ),
            asker,
        )

        assert len(domain_notifications) == 1, "one send call, not one per professional"
        recipients, query_id = domain_notifications[0]
        assert sorted(recipients) == sorted(pro.email for pro in domain_pros)
        assert query_id == response.id

    def test_domain_question_skips_professionals_who_do_not_serve_the_asker(
        self,
        db_session: Session,
        domain_notifications: list[tuple[list[str], str]],
    ) -> None:
        """Batching must not widen the audience: same filter, one call."""
        asker = _make_asker(
            db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        serves = _make_professional(
            db_session,
            email="serves@example.com",
            domain=ProfessionalDomain.RABBI,
            groups=["widow"],
            sectors=["sephardic"],
        )
        _make_professional(
            db_session,
            email="other-group@example.com",
            domain=ProfessionalDomain.RABBI,
            groups=["widower"],
        )
        _make_professional(
            db_session,
            email="other-domain@example.com",
            domain=ProfessionalDomain.LAWYER,
        )
        _make_professional(
            db_session,
            email="inactive@example.com",
            domain=ProfessionalDomain.RABBI,
            is_active=False,
        )

        professional_service.create_query(
            db_session,
            ProfessionalQueryCreate(
                content="שאלה כללית שמיועדת רק לחלק מהרבנים",
                domain=ProfessionalDomain.RABBI,
            ),
            asker,
        )

        assert [recipients for recipients, _ in domain_notifications] == [
            [serves.email]
        ]

    def test_domain_with_no_matching_professional_still_sends_nothing(
        self,
        db_session: Session,
        domain_notifications: list[tuple[list[str], str]],
    ) -> None:
        """
        The empty list reaches email_service, which opens no session for it —
        the question is still created, and nobody is emailed.
        """
        asker = _make_asker(db_session)

        professional_service.create_query(
            db_session,
            ProfessionalQueryCreate(
                content="שאלה בתחום שאין בו אף איש מקצוע",
                domain=ProfessionalDomain.MEDICINE,
            ),
            asker,
        )

        assert [recipients for recipients, _ in domain_notifications] == [[]]

    def test_direct_question_notifies_only_the_chosen_professional(
        self,
        db_session: Session,
        direct_notifications: list[tuple[str, str]],
        domain_notifications: list[tuple[list[str], str]],
    ) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session, domain=ProfessionalDomain.RABBI)
        _make_professional(
            db_session,
            email="colleague@example.com",
            domain=ProfessionalDomain.RABBI,
        )

        response = professional_service.create_query(
            db_session,
            ProfessionalQueryCreate(
                content="שאלה שמופנית לאיש מקצוע אחד בלבד",
                professional_id=professional.id,
            ),
            asker,
        )

        assert direct_notifications == [(professional.email, response.id)]
        assert domain_notifications == []


class TestGetMyQuestions:
    def test_returns_only_own_questions_newest_first(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        other = _make_asker(db_session, email="other@example.com")

        first = professional_service.create_query(
            db_session,
            ProfessionalQueryCreate(
                content="שאלה ראשונה שנשאלה על ידי המשתמש",
                domain=ProfessionalDomain.RABBI,
            ),
            asker,
        )
        second = professional_service.create_query(
            db_session,
            ProfessionalQueryCreate(
                content="שאלה שנייה שנשאלה על ידי המשתמש",
                domain=ProfessionalDomain.RABBI,
            ),
            asker,
        )
        professional_service.create_query(
            db_session,
            ProfessionalQueryCreate(
                content="שאלה של משתמש אחר לגמרי", domain=ProfessionalDomain.RABBI
            ),
            other,
        )

        # SQLite's default timestamp resolution can make same-transaction
        # inserts tie on created_at — set them explicitly so DESC ordering
        # is deterministic, mirroring the pattern in test_user_service.py.
        now = datetime.now(UTC)
        db_session.query(ProfessionalQuery).filter(
            ProfessionalQuery.id == first.id
        ).update({"created_at": now - timedelta(minutes=1)})
        db_session.query(ProfessionalQuery).filter(
            ProfessionalQuery.id == second.id
        ).update({"created_at": now})
        db_session.commit()

        results = professional_service.get_my_questions(db_session, asker)

        assert len(results) == 2
        assert all(r.asker_alias == "אלמנה – ספרדי" for r in results)
        assert results[0].content == "שאלה שנייה שנשאלה על ידי המשתמש"
        assert results[1].content == "שאלה ראשונה שנשאלה על ידי המשתמש"


class TestGetPendingQuestions:
    def test_returns_question_addressed_to_this_professional(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        _make_query(db_session, asker, professional=professional)

        results = professional_service.get_pending_questions(db_session, professional)

        assert len(results) == 1
        assert results[0].status == QueryStatus.OPEN

    def test_returns_general_question_in_own_domain(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session, domain=ProfessionalDomain.RABBI)
        _make_query(db_session, asker, domain=ProfessionalDomain.RABBI)

        results = professional_service.get_pending_questions(db_session, professional)

        assert len(results) == 1
        assert results[0].domain == ProfessionalDomain.RABBI

    def test_excludes_general_question_of_another_domain(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session, domain=ProfessionalDomain.LAWYER)
        _make_query(db_session, asker, domain=ProfessionalDomain.MEDICINE)

        assert (
            professional_service.get_pending_questions(db_session, professional) == []
        )

    def test_excludes_question_addressed_to_another_professional(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        colleague = _make_professional(db_session, email="colleague@example.com")
        _make_query(db_session, asker, professional=colleague)

        assert (
            professional_service.get_pending_questions(db_session, professional) == []
        )

    def test_excludes_already_answered_question(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        _make_query(
            db_session, asker, professional=professional, status=QueryStatus.ANSWERED
        )

        assert (
            professional_service.get_pending_questions(db_session, professional) == []
        )

    def test_excludes_asker_outside_assigned_groups_or_sectors(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(
            db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        professional = _make_professional(
            db_session, domain=ProfessionalDomain.RABBI, groups=["widower"]
        )
        _make_query(db_session, asker, domain=ProfessionalDomain.RABBI)

        assert (
            professional_service.get_pending_questions(db_session, professional) == []
        )

    def test_includes_asker_inside_assigned_groups_and_sectors(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(
            db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        professional = _make_professional(
            db_session,
            domain=ProfessionalDomain.RABBI,
            groups=["widow", "widower"],
            sectors=["sephardic"],
        )
        _make_query(db_session, asker, domain=ProfessionalDomain.RABBI)

        assert (
            len(professional_service.get_pending_questions(db_session, professional))
            == 1
        )

    def test_orders_longest_waiting_first(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        older = _make_query(
            db_session,
            asker,
            professional=professional,
            content="השאלה שממתינה הכי הרבה זמן",
        )
        newer = _make_query(
            db_session,
            asker,
            professional=professional,
            content="השאלה שהגיעה ממש עכשיו",
        )

        # SQLite's default timestamp resolution can make same-transaction
        # inserts tie on created_at — set them explicitly so ASC ordering
        # is deterministic, as in TestGetMyQuestions above.
        now = datetime.now(UTC)
        db_session.query(ProfessionalQuery).filter(
            ProfessionalQuery.id == older.id
        ).update({"created_at": now - timedelta(minutes=1)})
        db_session.query(ProfessionalQuery).filter(
            ProfessionalQuery.id == newer.id
        ).update({"created_at": now})
        db_session.commit()

        results = professional_service.get_pending_questions(db_session, professional)

        assert [r.content for r in results] == [
            "השאלה שממתינה הכי הרבה זמן",
            "השאלה שהגיעה ממש עכשיו",
        ]

    def test_hides_the_askers_real_name_by_default(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        _make_query(db_session, asker, professional=professional)

        results = professional_service.get_pending_questions(db_session, professional)

        assert results[0].asker is None
        assert results[0].asker_alias == "אלמנה – ספרדי"

    def test_reveals_the_askers_name_when_they_chose_to(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        _make_query(db_session, asker, professional=professional, show_real_name=True)

        results = professional_service.get_pending_questions(db_session, professional)

        assert results[0].asker is not None
        assert results[0].asker.id == asker.id


class TestGetPublicQA:
    def test_excludes_private_and_unanswered_questions(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(db_session)
        _make_query(db_session, asker, is_public=False, status=QueryStatus.ANSWERED)
        _make_query(db_session, asker, is_public=True, status=QueryStatus.OPEN)
        _make_query(db_session, asker, is_public=True, status=QueryStatus.CLOSED)
        visible = _make_query(
            db_session,
            asker,
            is_public=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה לשאלה הציבורית היחידה שנענתה",
        )

        results = professional_service.get_public_qa(db_session, asker)

        assert [r.id for r in results] == [visible.id]

    def test_shows_the_answering_professional_by_name(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        _make_query(
            db_session,
            asker,
            professional=professional,
            is_public=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה מהמקצוען שאמור להופיע בשמו",
        )

        results = professional_service.get_public_qa(db_session, asker)

        assert results[0].professional is not None
        assert results[0].professional.id == professional.id

    def test_hides_the_askers_real_name_by_default(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        _make_query(
            db_session,
            asker,
            is_public=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה לשאלה שנשארת אנונימית מבחינת השואלת",
        )

        results = professional_service.get_public_qa(db_session, asker)

        assert results[0].asker is None
        assert results[0].asker_alias == "אלמנה – ספרדי"

    def test_reveals_the_askers_name_when_they_chose_to(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(db_session)
        _make_query(
            db_session,
            asker,
            is_public=True,
            show_real_name=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה לשאלה שבה השואלת בחרה לחשוף את שמה",
        )

        results = professional_service.get_public_qa(db_session, asker)

        assert results[0].asker is not None
        assert results[0].asker.id == asker.id

    def test_same_cell_user_sees_it_different_cell_does_not(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(
            db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        _make_query(
            db_session,
            asker,
            is_public=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה גלויה לבני התא של השואלת",
        )
        same_cell = _make_asker(
            db_session,
            email="same-cell@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        other_cell = _make_asker(
            db_session,
            email="other-cell@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )

        assert len(professional_service.get_public_qa(db_session, same_cell)) == 1
        assert professional_service.get_public_qa(db_session, other_cell) == []

    def test_admin_sees_every_cell(self, db_session: Session) -> None:
        first_cell_asker = _make_asker(
            db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        second_cell_asker = _make_asker(
            db_session,
            email="other-cell-asker@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        _make_query(
            db_session,
            first_cell_asker,
            is_public=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה בתא הראשון",
        )
        _make_query(
            db_session,
            second_cell_asker,
            is_public=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה בתא השני",
        )
        admin = _make_asker(
            db_session, email="admin@example.com", user_type=None, sector=None
        )
        admin.role = UserRole.ADMIN
        db_session.commit()

        assert len(professional_service.get_public_qa(db_session, admin)) == 2

    def test_domain_filter_applied_when_given_ignored_when_not(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(db_session)
        _make_query(
            db_session,
            asker,
            domain=ProfessionalDomain.RABBI,
            is_public=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה של רב לשאלה",
            content="שאלה בתחום הרבנות שנשאלה",
        )
        _make_query(
            db_session,
            asker,
            domain=ProfessionalDomain.LAWYER,
            is_public=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה של עורך דין לשאלה",
            content="שאלה בתחום המשפטי שנשאלה",
        )

        assert len(professional_service.get_public_qa(db_session, asker)) == 2
        filtered = professional_service.get_public_qa(
            db_session, asker, domain=ProfessionalDomain.RABBI
        )
        assert len(filtered) == 1
        assert filtered[0].domain == ProfessionalDomain.RABBI

    def test_pagination(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        queries = [
            _make_query(
                db_session,
                asker,
                is_public=True,
                status=QueryStatus.ANSWERED,
                answer=f"תשובה מספר {i}",
                content=f"שאלה ציבורית מספר {i} ברשימה",
            )
            for i in range(5)
        ]
        # created_at ties under SQLite's default resolution — space them out
        # so page ordering (newest first) is deterministic, as elsewhere.
        now = datetime.now(UTC)
        for offset, query in enumerate(queries):
            db_session.query(ProfessionalQuery).filter(
                ProfessionalQuery.id == query.id
            ).update({"created_at": now - timedelta(minutes=len(queries) - offset)})
        db_session.commit()

        first_page = professional_service.get_public_qa(
            db_session, asker, page=1, page_size=2
        )
        second_page = professional_service.get_public_qa(
            db_session, asker, page=2, page_size=2
        )

        assert [r.id for r in first_page] == [queries[4].id, queries[3].id]
        assert [r.id for r in second_page] == [queries[2].id, queries[1].id]

    def test_like_count_and_liked_by_me(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        liker = _make_asker(db_session, email="liker@example.com")
        non_liker = _make_asker(db_session, email="non-liker@example.com")
        query = _make_query(
            db_session,
            asker,
            is_public=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה שתקבל לייק אחד",
        )
        like_service.toggle_like(
            db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, liker
        )

        as_liker = professional_service.get_public_qa(db_session, liker)
        as_non_liker = professional_service.get_public_qa(db_session, non_liker)

        assert as_liker[0].like_count == 1
        assert as_liker[0].liked_by_me is True
        assert as_non_liker[0].like_count == 1
        assert as_non_liker[0].liked_by_me is False

    def test_like_count_and_liked_by_me_avoid_n_plus_one(
        self, db_session: Session, db_engine: Engine
    ) -> None:
        """
        like_count/liked_by_me must come from one SELECT for the whole page,
        not one extra query per row — the same concern the "one send call,
        not one per professional" tests above pin for email notifications.
        """
        asker = _make_asker(db_session)
        viewer = _make_asker(db_session, email="viewer@example.com")
        queries = [
            _make_query(
                db_session,
                asker,
                is_public=True,
                status=QueryStatus.ANSWERED,
                answer=f"תשובה מספר {i}",
                content=f"שאלה ציבורית מספר {i} לבדיקת ביצועים",
            )
            for i in range(5)
        ]
        for query in queries[:3]:
            like_service.toggle_like(
                db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, viewer
            )

        # Force any pending lazy-refresh of `viewer` (its attributes were
        # expired by the commits above) to happen now, outside the counted
        # window below — get_public_qa() reads viewer.role/user_type/sector,
        # and that first touch would otherwise cost its own SELECT unrelated
        # to the per-row concern this test is actually pinning.
        _ = (viewer.role, viewer.user_type, viewer.sector)

        statements: list[str] = []

        def _record(
            conn: Connection,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(db_engine, "before_cursor_execute", _record)
        try:
            results = professional_service.get_public_qa(db_session, viewer)
        finally:
            event.remove(db_engine, "before_cursor_execute", _record)

        assert len(results) == 5
        select_statements = [
            s for s in statements if s.strip().upper().startswith("SELECT")
        ]
        assert len(select_statements) == 1, (
            "expected a single SELECT for the whole page, not one per row"
        )

    def test_asker_profile_change_after_creation_does_not_move_the_question(
        self, db_session: Session
    ) -> None:
        """
        The visible cell is the one frozen onto the question when it was
        created, not the asker's current profile — changing the asker's
        user_type/sector afterwards must not move an existing question to a
        different cell's feed.
        """
        asker = _make_asker(
            db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        query = _make_query(
            db_session,
            asker,
            is_public=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה לשאלה שנשאלה בתא המקורי",
            content="שאלה שנשאלה בתא המקורי של השואלת",
        )

        asker.user_type = UserType.WIDOWER
        asker.sector = Sector.HASIDIC
        db_session.commit()

        original_cell_viewer = _make_asker(
            db_session,
            email="original-cell@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        new_cell_viewer = _make_asker(
            db_session,
            email="new-cell@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )

        assert [
            r.id
            for r in professional_service.get_public_qa(
                db_session, original_cell_viewer
            )
        ] == [query.id]
        assert professional_service.get_public_qa(db_session, new_cell_viewer) == []

    def test_skips_a_malformed_answered_row_instead_of_raising(
        self, db_session: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        status=ANSWERED should always come with an answer (answer_query()
        sets both together) — but if that invariant is ever violated, e.g. by
        a manual DB edit, one malformed row must not 500 the whole feed for
        everyone. It's skipped and logged instead.
        """
        asker = _make_asker(db_session)
        _make_query(
            db_session, asker, is_public=True, status=QueryStatus.ANSWERED, answer=None
        )
        good = _make_query(
            db_session,
            asker,
            is_public=True,
            status=QueryStatus.ANSWERED,
            answer="תשובה תקינה לשאלה השנייה",
        )

        with caplog.at_level("ERROR"):
            results = professional_service.get_public_qa(db_session, asker)

        assert [r.id for r in results] == [good.id]
        assert "skipping" in caplog.text


class TestAnswerQuery:
    def test_stores_the_answer_and_closes_the_question(
        self, db_session: Session, sent_answer_emails: list[tuple[str, str]]
    ) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        query = _make_query(db_session, asker, professional=professional)

        response = professional_service.answer_query(
            db_session,
            query.id,
            ProfessionalAnswerRequest(answer="זו התשובה המקצועית לשאלה שנשאלה"),
            professional,
        )

        assert response.answer == "זו התשובה המקצועית לשאלה שנשאלה"
        assert response.status == QueryStatus.ANSWERED
        assert response.answered_at is not None

        stored = db_session.get(ProfessionalQuery, query.id)
        assert stored is not None
        assert stored.status == QueryStatus.ANSWERED
        assert stored.answer == "זו התשובה המקצועית לשאלה שנשאלה"
        assert stored.answered_at is not None

    def test_notifies_the_asker(
        self, db_session: Session, sent_answer_emails: list[tuple[str, str]]
    ) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        query = _make_query(db_session, asker, professional=professional)

        professional_service.answer_query(
            db_session,
            query.id,
            ProfessionalAnswerRequest(answer="תשובה מלאה ומפורטת לשואל"),
            professional,
        )

        assert sent_answer_emails == [(asker.email, query.id)]

    def test_domain_professional_may_answer_a_general_question(
        self, db_session: Session, sent_answer_emails: list[tuple[str, str]]
    ) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session, domain=ProfessionalDomain.RABBI)
        query = _make_query(db_session, asker, domain=ProfessionalDomain.RABBI)

        response = professional_service.answer_query(
            db_session,
            query.id,
            ProfessionalAnswerRequest(answer="תשובה לשאלה הכללית שנשאלה בתחום"),
            professional,
        )

        assert response.status == QueryStatus.ANSWERED

    def test_rejects_unknown_query_id(self, db_session: Session) -> None:
        professional = _make_professional(db_session)

        with pytest.raises(HTTPException) as exc_info:
            professional_service.answer_query(
                db_session,
                "00000000-0000-0000-0000-000000000000",
                ProfessionalAnswerRequest(answer="תשובה לשאלה שאיננה קיימת"),
                professional,
            )
        assert exc_info.value.status_code == 404

    def test_rejects_professional_who_is_not_the_target(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session)
        colleague = _make_professional(db_session, email="colleague@example.com")
        query = _make_query(db_session, asker, professional=colleague)

        with pytest.raises(HTTPException) as exc_info:
            professional_service.answer_query(
                db_session,
                query.id,
                ProfessionalAnswerRequest(answer="תשובה לשאלה שהופנתה לעמית אחר"),
                professional,
            )
        assert exc_info.value.status_code == 403

    def test_rejects_general_question_from_an_asker_outside_the_scope(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(
            db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        professional = _make_professional(
            db_session, domain=ProfessionalDomain.RABBI, sectors=["hasidic"]
        )
        query = _make_query(db_session, asker, domain=ProfessionalDomain.RABBI)

        with pytest.raises(HTTPException) as exc_info:
            professional_service.answer_query(
                db_session,
                query.id,
                ProfessionalAnswerRequest(answer="תשובה לשואלת שאינה בתחום אחריותי"),
                professional,
            )
        assert exc_info.value.status_code == 403

    def test_rejects_a_question_that_was_already_answered(
        self, db_session: Session, sent_answer_emails: list[tuple[str, str]]
    ) -> None:
        asker = _make_asker(db_session)
        professional = _make_professional(db_session, domain=ProfessionalDomain.RABBI)
        colleague = _make_professional(
            db_session, email="colleague@example.com", domain=ProfessionalDomain.RABBI
        )
        query = _make_query(db_session, asker, domain=ProfessionalDomain.RABBI)
        professional_service.answer_query(
            db_session,
            query.id,
            ProfessionalAnswerRequest(answer="התשובה הראשונה שהוגשה לשאלה"),
            professional,
        )

        with pytest.raises(HTTPException) as exc_info:
            professional_service.answer_query(
                db_session,
                query.id,
                ProfessionalAnswerRequest(answer="תשובה שנייה שמנסה לדרוס את הראשונה"),
                colleague,
            )
        assert exc_info.value.status_code == 409

        stored = db_session.get(ProfessionalQuery, query.id)
        assert stored is not None
        assert stored.answer == "התשובה הראשונה שהוגשה לשאלה"
        assert len(sent_answer_emails) == 1


class TestToggleLike:
    def test_first_like_then_toggle_removes_it(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        liker = _make_asker(db_session, email="liker@example.com")
        query = _make_query(
            db_session, asker, status=QueryStatus.ANSWERED, is_public=True
        )

        liked = like_service.toggle_like(
            db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, liker
        )
        assert liked.liked is True
        assert liked.like_count == 1
        assert db_session.query(Like).count() == 1

        unliked = like_service.toggle_like(
            db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, liker
        )
        assert unliked.liked is False
        assert unliked.like_count == 0
        assert db_session.query(Like).count() == 0

    def test_two_different_users_both_count(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        first_liker = _make_asker(db_session, email="liker1@example.com")
        second_liker = _make_asker(db_session, email="liker2@example.com")
        query = _make_query(
            db_session, asker, status=QueryStatus.ANSWERED, is_public=True
        )

        like_service.toggle_like(
            db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, first_liker
        )
        result = like_service.toggle_like(
            db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, second_liker
        )

        assert result.like_count == 2

    def test_asker_may_like_their_own_question(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        query = _make_query(db_session, asker, status=QueryStatus.ANSWERED)

        result = like_service.toggle_like(
            db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, asker
        )

        assert result.liked is True

    def test_admin_may_like_any_question_regardless_of_cell(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(
            db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        admin = _make_asker(
            db_session,
            email="admin@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        admin.role = UserRole.ADMIN
        db_session.commit()
        query = _make_query(
            db_session, asker, status=QueryStatus.ANSWERED, is_public=False
        )

        result = like_service.toggle_like(
            db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, admin
        )

        assert result.liked is True

    def test_outsider_rejected_on_private_question(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        outsider = _make_asker(db_session, email="outsider@example.com")
        query = _make_query(
            db_session, asker, status=QueryStatus.ANSWERED, is_public=False
        )

        with pytest.raises(HTTPException) as exc_info:
            like_service.toggle_like(
                db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, outsider
            )
        assert exc_info.value.status_code == 403

    def test_outsider_rejected_on_public_question_outside_the_askers_cell(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(
            db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        outsider = _make_asker(
            db_session,
            email="outsider@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        query = _make_query(
            db_session, asker, status=QueryStatus.ANSWERED, is_public=True
        )

        with pytest.raises(HTTPException) as exc_info:
            like_service.toggle_like(
                db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, outsider
            )
        assert exc_info.value.status_code == 403

    def test_user_in_askers_cell_may_like_public_question(
        self, db_session: Session
    ) -> None:
        asker = _make_asker(
            db_session, user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        same_cell_user = _make_asker(
            db_session,
            email="same-cell@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        query = _make_query(
            db_session, asker, status=QueryStatus.ANSWERED, is_public=True
        )

        result = like_service.toggle_like(
            db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, same_cell_user
        )

        assert result.liked is True

    def test_rejects_open_question(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        query = _make_query(db_session, asker, status=QueryStatus.OPEN)

        with pytest.raises(HTTPException) as exc_info:
            like_service.toggle_like(
                db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, asker
            )
        assert exc_info.value.status_code == 409

    def test_rejects_closed_question(self, db_session: Session) -> None:
        asker = _make_asker(db_session)
        query = _make_query(db_session, asker, status=QueryStatus.CLOSED)

        with pytest.raises(HTTPException) as exc_info:
            like_service.toggle_like(
                db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, asker
            )
        assert exc_info.value.status_code == 409

    def test_unliking_still_works_after_question_is_closed(
        self, db_session: Session
    ) -> None:
        """
        The ANSWERED requirement must only block creating a new like — once a
        like exists, its owner must always be able to remove it, even if the
        question's status later moves on to CLOSED. Otherwise a like becomes
        permanently stuck with no way to undo it.
        """
        asker = _make_asker(db_session)
        query = _make_query(db_session, asker, status=QueryStatus.ANSWERED)

        liked = like_service.toggle_like(
            db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, asker
        )
        assert liked.liked is True

        query.status = QueryStatus.CLOSED
        db_session.commit()

        unliked = like_service.toggle_like(
            db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, asker
        )
        assert unliked.liked is False
        assert db_session.query(Like).count() == 0

    def test_denies_when_asker_or_viewer_has_no_cell_set(
        self, db_session: Session
    ) -> None:
        """
        A None user_type/sector must never accidentally match another None
        via `None == None` — a stranger with no profile cell must not be
        granted access to a public question just because both sides are
        unset (User.user_type/sector are nullable columns).
        """
        asker = _make_asker(db_session, user_type=None, sector=None)
        stranger = _make_asker(
            db_session, email="stranger@example.com", user_type=None, sector=None
        )
        query = _make_query(
            db_session, asker, status=QueryStatus.ANSWERED, is_public=True
        )

        with pytest.raises(HTTPException) as exc_info:
            like_service.toggle_like(
                db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, stranger
            )
        assert exc_info.value.status_code == 403

    def test_rejects_unknown_query_id(self, db_session: Session) -> None:
        asker = _make_asker(db_session)

        with pytest.raises(HTTPException) as exc_info:
            like_service.toggle_like(
                db_session,
                LikeTargetType.PROFESSIONAL_QUERY,
                "00000000-0000-0000-0000-000000000000",
                asker,
            )
        assert exc_info.value.status_code == 404

    def test_concurrent_double_click_does_not_raise_500(
        self, db_session: Session
    ) -> None:
        """
        Simulates two requests racing to like the same target: toggle_like()'s
        own SELECT finds no existing row, but by the time its INSERT reaches
        the DB a competing row for the same (user, target_type, target_id) is
        already there — the composite primary key rejects it, and toggle_like()
        must catch that and answer normally instead of a 500.

        The test's single shared SQLite connection (see conftest.db_engine)
        means the injected competing row lives in the same transaction as our
        own failed INSERT, so it is undone by the same rollback — this only
        asserts the IntegrityError is caught rather than propagated, not the
        resulting count (a real second session's row would survive that
        rollback, since it was already committed independently).
        """
        asker = _make_asker(db_session)
        liker = _make_asker(db_session, email="liker@example.com")
        query = _make_query(
            db_session, asker, status=QueryStatus.ANSWERED, is_public=True
        )

        def sneak_in_competing_row(
            mapper: Mapper[Like], connection: Connection, target: Like
        ) -> None:
            connection.execute(
                insert(Like).values(
                    user_id=liker.id,
                    target_type=LikeTargetType.PROFESSIONAL_QUERY,
                    target_id=query.id,
                )
            )

        event.listen(Like, "before_insert", sneak_in_competing_row)
        try:
            result = like_service.toggle_like(
                db_session, LikeTargetType.PROFESSIONAL_QUERY, query.id, liker
            )
        finally:
            event.remove(Like, "before_insert", sneak_in_competing_row)

        assert result.liked is True
        assert isinstance(result.like_count, int)
