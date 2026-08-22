"""
Unit tests for professional_service.create_query(), get_my_questions(),
get_pending_questions() and answer_query().
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.constants import (
    ProfessionalDomain,
    QueryStatus,
    Sector,
    UserRole,
    UserType,
)
from app.models.professional import ProfessionalQuery
from app.models.user import User
from app.schemas.professional import ProfessionalAnswerRequest, ProfessionalQueryCreate
from app.services import email_service, professional_service


def _make_asker(
    db_session: Session,
    email: str = "asker@example.com",
    user_type: UserType = UserType.WIDOW,
    sector: Sector = Sector.SEPHARDIC,
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
) -> ProfessionalQuery:
    query = ProfessionalQuery(
        asker_id=asker.id,
        professional_id=professional.id if professional is not None else None,
        domain=domain,
        content=content,
        status=status,
        show_real_name=show_real_name,
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
