"""
Unit tests for professional_service.create_query() and get_my_questions().
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
from app.schemas.professional import ProfessionalQueryCreate
from app.services import professional_service


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
