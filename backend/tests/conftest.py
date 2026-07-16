import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all models with Base.metadata
from app.core.constants import Sector, UserRole, UserType
from app.core.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models.user import User


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # single shared connection — required for in-memory SQLite
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
async def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db_session):
    """Factory fixture for creating a User row with a consistent signature."""

    def _make(
        email: str,
        user_type: UserType | None = None,
        sector: Sector | None = None,
        role: UserRole = UserRole.USER,
    ) -> User:
        user = User(
            email=email,
            password_hash="hashed",
            first_name="Test",
            last_name="User",
            role=role,
            user_type=user_type,
            sector=sector,
        )
        db_session.add(user)
        db_session.commit()
        return user

    return _make
