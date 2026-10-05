import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all models with Base.metadata
from app.core.config import settings
from app.core.constants import (
    AccountStatus,
    GroupVisibility,
    ProfessionalDomain,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models.agent import AgentDomain
from app.models.user import User

# ---------------------------------------------------------------------------
# PostgreSQL, for the tests SQLite cannot answer
# ---------------------------------------------------------------------------
#
# Embeddings need pgvector's VECTOR type and its distance operators, which have
# no SQLite equivalent. Those tests read this variable and skip without it.
#
# An explicit variable rather than "try to connect, skip if it fails": a silent
# connection attempt turns a broken CI database into a green run with the tests
# quietly not executed, which is the failure mode this is set up to avoid. CI
# sets it (see .github/workflows/ci.yml), so a skip there is a red flag, not
# background noise.
POSTGRES_TEST_URL_ENV = "TEST_POSTGRES_URL"

# This fixture drops every table before and after each test, so the database it
# points at must be one whose contents nobody minds losing. `docker compose up
# db` gives you the *development* database on the same host and port — pointing
# this at it would empty the data you have been working with. Create a separate
# one next to it:
#
#   docker compose up -d db
#   docker compose exec db createdb -U user anu_banayich_test
#   TEST_POSTGRES_URL=postgresql+psycopg2://user:password@localhost:5432/anu_banayich_test
#
# CI uses the same separate name (.github/workflows/ci.yml).
POSTGRES_TEST_URL_EXAMPLE = (
    "postgresql+psycopg2://user:password@localhost:5432/anu_banayich_test"
)


@pytest.fixture
def pg_engine():
    """A PostgreSQL engine with the vector extension and every table created."""
    url = os.getenv(POSTGRES_TEST_URL_ENV)
    if not url:
        pytest.skip(
            f"{POSTGRES_TEST_URL_ENV} is not set — this test needs PostgreSQL "
            f"with pgvector. Point it at a throwaway database, e.g. "
            f"{POSTGRES_TEST_URL_EXAMPLE}"
        )

    # The guard that matters more than the message above: this fixture is about
    # to drop every table, and the one database we can positively identify as
    # not-throwaway is the one the application itself is configured to use.
    # Refusing here costs a developer thirty seconds; not refusing costs them
    # their local data, once, silently, on a command they ran to check a test.
    if url == settings.DATABASE_URL:
        raise RuntimeError(
            f"{POSTGRES_TEST_URL_ENV} is the same database as DATABASE_URL "
            f"({url}). These tests drop every table — point them at a separate "
            f"database, e.g. {POSTGRES_TEST_URL_EXAMPLE}"
        )

    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    # Ahead of create_all as well as after: a previous run killed part-way
    # through leaves tables behind, and the next run has to start clean.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


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
        account_status: AccountStatus = AccountStatus.PENDING_OTP,
        professional_domain: ProfessionalDomain | None = None,
        # Which cells a PROFESSIONAL is assigned to. Default None, matching the
        # column: a professional with no assignment reaches nobody, and
        # ABF-156 reads these to decide which cells she may convene.
        professional_groups: list[str] | None = None,
        professional_sectors: list[str] | None = None,
    ) -> User:
        user = User(
            email=email,
            password_hash="hashed",
            first_name="Test",
            last_name="User",
            role=role,
            user_type=user_type,
            sector=sector,
            account_status=account_status,
            professional_domain=professional_domain,
            professional_groups=professional_groups,
            professional_sectors=professional_sectors,
        )
        db_session.add(user)
        db_session.commit()
        return user

    return _make


@pytest.fixture
def make_agent_domain(db_session):
    """Factory fixture for an AgentDomain row.

    professional_domain is the field that matters to most callers — it is what
    decides which professional may edit the domain's knowledge base — so it
    leads, and the group/sector visibility that only the member-facing catalog
    reads defaults to ALL.
    """

    def _make(
        name: str = "זכויות",
        professional_domain: ProfessionalDomain = ProfessionalDomain.LAWYER,
        group_visibility: GroupVisibility = GroupVisibility.ALL,
        sector_visibility: SectorVisibility = SectorVisibility.ALL,
        *,
        is_active: bool = True,
    ) -> AgentDomain:
        domain = AgentDomain(
            name=name,
            description=f"תיאור עבור {name}",
            professional_domain=professional_domain,
            group_visibility=group_visibility,
            sector_visibility=sector_visibility,
            is_active=is_active,
        )
        db_session.add(domain)
        db_session.commit()
        return domain

    return _make
