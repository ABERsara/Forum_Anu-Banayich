"""
SQLAlchemy declarative base.

All ORM models inherit from Base.
Import this (not the models directly) in alembic/env.py so that
autogenerate detects all tables.

Usage in models:
    from app.db.base import Base
    class MyModel(Base):
        __tablename__ = "my_table"
        ...
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
