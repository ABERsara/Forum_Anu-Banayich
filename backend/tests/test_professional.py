"""
Integration tests for the /advice/questions endpoints.
"""

import pytest
from sqlalchemy.orm import Session

from app.core.constants import (
    ProfessionalDomain,
    QueryStatus,
    Sector,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.professional import ProfessionalQuery
from app.models.user import User
from app.services import email_service

BASE = "/api/v1/advice"


def _make_user(
    db_session: Session,
    role: UserRole,
    email: str,
    user_type: UserType | None = None,
    sector: Sector | None = None,
    **kwargs: object,
) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        user_type=user_type,
        sector=sector,
        **kwargs,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def as_user():
    """Override get_current_user and get_current_active_user to return the given user."""

    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


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


class TestAskQuestion:
    async def test_ask_general_domain_question(
        self, client, db_session, as_user
    ) -> None:
        asker = _make_user(
            db_session,
            UserRole.USER,
            "asker@example.com",
            UserType.WIDOW,
            Sector.SEPHARDIC,
        )
        as_user(asker)

        response = await client.post(
            f"{BASE}/questions",
            json={
                "content": "יש לי שאלה כללית בנושא ירושה ורכוש",
                "domain": ProfessionalDomain.LAWYER.value,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["domain"] == ProfessionalDomain.LAWYER.value
        assert body["professional"] is None
        assert body["asker"] is None

    async def test_ask_specific_professional(self, client, db_session, as_user) -> None:
        asker = _make_user(
            db_session,
            UserRole.USER,
            "asker2@example.com",
            UserType.WIDOW,
            Sector.SEPHARDIC,
        )
        professional = _make_user(
            db_session,
            UserRole.PROFESSIONAL,
            "pro@example.com",
            professional_domain=ProfessionalDomain.LAWYER,
            professional_groups=["all"],
            professional_sectors=["all"],
            is_active_professional=True,
        )
        as_user(asker)

        response = await client.post(
            f"{BASE}/questions",
            json={
                "content": "שאלה ישירה לאיש מקצוע ספציפי",
                "professional_id": professional.id,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["professional"]["id"] == professional.id

    async def test_rejects_missing_professional_and_domain(
        self, client, db_session, as_user
    ) -> None:
        asker = _make_user(db_session, UserRole.USER, "asker3@example.com")
        as_user(asker)

        response = await client.post(
            f"{BASE}/questions", json={"content": "שאלה בלי יעד בכלל ולא ברור למי"}
        )

        assert response.status_code == 400


class TestMyQuestions:
    async def test_returns_only_current_users_questions(
        self, client, db_session, as_user
    ) -> None:
        asker = _make_user(
            db_session,
            UserRole.USER,
            "asker4@example.com",
            UserType.WIDOW,
            Sector.SEPHARDIC,
        )
        other = _make_user(db_session, UserRole.USER, "asker5@example.com")
        as_user(asker)

        await client.post(
            f"{BASE}/questions",
            json={
                "content": "שאלה ראשונה של המשתמש הנוכחי",
                "domain": ProfessionalDomain.RABBI.value,
            },
        )

        as_user(other)
        await client.post(
            f"{BASE}/questions",
            json={
                "content": "שאלה של משתמש אחר לגמרי",
                "domain": ProfessionalDomain.RABBI.value,
            },
        )

        as_user(asker)
        response = await client.get(f"{BASE}/questions")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["content"] == "שאלה ראשונה של המשתמש הנוכחי"


def _make_professional(
    db_session: Session,
    email: str = "pro@example.com",
    domain: ProfessionalDomain = ProfessionalDomain.LAWYER,
) -> User:
    return _make_user(
        db_session,
        UserRole.PROFESSIONAL,
        email,
        professional_domain=domain,
        professional_groups=["all"],
        professional_sectors=["all"],
        is_active_professional=True,
    )


class TestPendingQuestions:
    async def test_returns_questions_targeting_the_professional(
        self, client, db_session, as_user
    ) -> None:
        asker = _make_user(
            db_session,
            UserRole.USER,
            "asker6@example.com",
            UserType.WIDOW,
            Sector.SEPHARDIC,
        )
        professional = _make_professional(db_session)
        colleague = _make_professional(
            db_session, "pro2@example.com", ProfessionalDomain.MEDICINE
        )

        as_user(asker)
        await client.post(
            f"{BASE}/questions",
            json={
                "content": "שאלה משפטית שממתינה לאיש המקצוע",
                "professional_id": professional.id,
            },
        )
        await client.post(
            f"{BASE}/questions",
            json={
                "content": "שאלה רפואית שאינה שייכת לעורך הדין",
                "professional_id": colleague.id,
            },
        )

        as_user(professional)
        response = await client.get(f"{BASE}/questions/pending")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["content"] == "שאלה משפטית שממתינה לאיש המקצוע"
        # Privacy: the professional sees the alias, never the asker's name.
        assert body[0]["asker"] is None
        assert body[0]["asker_alias"] == "אלמנה – ספרדי"

    async def test_forbidden_for_a_regular_user(
        self, client, db_session, as_user
    ) -> None:
        asker = _make_user(db_session, UserRole.USER, "asker7@example.com")
        as_user(asker)

        response = await client.get(f"{BASE}/questions/pending")

        assert response.status_code == 403


class TestAnswerQuestion:
    async def test_answering_stores_the_answer_and_emails_the_asker(
        self, client, db_session, as_user, sent_answer_emails
    ) -> None:
        asker = _make_user(
            db_session,
            UserRole.USER,
            "asker8@example.com",
            UserType.WIDOW,
            Sector.SEPHARDIC,
        )
        professional = _make_professional(db_session)

        as_user(asker)
        created = await client.post(
            f"{BASE}/questions",
            json={
                "content": "שאלה שתקבל תשובה מאיש המקצוע",
                "professional_id": professional.id,
            },
        )
        query_id = created.json()["id"]

        as_user(professional)
        response = await client.put(
            f"{BASE}/questions/{query_id}/answer",
            json={"answer": "זו התשובה המקצועית המלאה לשאלה"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["answer"] == "זו התשובה המקצועית המלאה לשאלה"
        assert body["status"] == QueryStatus.ANSWERED.value
        assert body["answered_at"] is not None

        stored = db_session.get(ProfessionalQuery, query_id)
        assert stored.status == QueryStatus.ANSWERED
        assert stored.answered_at is not None
        assert sent_answer_emails == [(asker.email, query_id)]

    async def test_forbidden_for_a_regular_user(
        self, client, db_session, as_user
    ) -> None:
        asker = _make_user(
            db_session,
            UserRole.USER,
            "asker9@example.com",
            UserType.WIDOW,
            Sector.SEPHARDIC,
        )
        professional = _make_professional(db_session)

        as_user(asker)
        created = await client.post(
            f"{BASE}/questions",
            json={
                "content": "שאלה שהשואל ינסה לענות עליה בעצמו",
                "professional_id": professional.id,
            },
        )
        query_id = created.json()["id"]

        response = await client.put(
            f"{BASE}/questions/{query_id}/answer",
            json={"answer": "תשובה שהשואל אינו רשאי להגיש"},
        )

        assert response.status_code == 403

    async def test_answering_twice_is_rejected(
        self, client, db_session, as_user, sent_answer_emails
    ) -> None:
        asker = _make_user(
            db_session,
            UserRole.USER,
            "asker10@example.com",
            UserType.WIDOW,
            Sector.SEPHARDIC,
        )
        professional = _make_professional(db_session)

        as_user(asker)
        created = await client.post(
            f"{BASE}/questions",
            json={
                "content": "שאלה שתיענה פעם אחת בלבד",
                "professional_id": professional.id,
            },
        )
        query_id = created.json()["id"]

        as_user(professional)
        first = await client.put(
            f"{BASE}/questions/{query_id}/answer",
            json={"answer": "התשובה הראשונה והיחידה לשאלה"},
        )
        second = await client.put(
            f"{BASE}/questions/{query_id}/answer",
            json={"answer": "תשובה נוספת שאמורה להידחות"},
        )

        assert first.status_code == 200
        assert second.status_code == 409
        assert len(sent_answer_emails) == 1
