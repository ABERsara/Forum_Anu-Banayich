"""
Integration tests for POST/GET /advice/questions.
"""

import pytest
from sqlalchemy.orm import Session

from app.core.constants import ProfessionalDomain, Sector, UserRole, UserType
from app.core.dependencies import get_current_user
from app.main import app
from app.models.user import User

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
    """Override get_current_user to return the given user, for the duration of the test."""

    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)


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
