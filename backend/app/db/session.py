"""
Database engine and session factory.

Use `get_db()` as a FastAPI dependency – see core/dependencies.py.

Never import SessionLocal directly into endpoints;
always go through the dependency.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    # SQLite-specific: allows the same connection to be used across threads.
    # Remove this line when switching to PostgreSQL.
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
