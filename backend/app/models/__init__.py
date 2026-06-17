"""
Import all models here so that SQLAlchemy and Alembic can discover them.

When you create a new model file, add it to this list.
"""

from app.models.audit import AuditLog
from app.models.document import Document
from app.models.forum import DirectMessage, ForumPost
from app.models.professional import ProfessionalQuery
from app.models.report import Report
from app.models.user import User

__all__ = [
    "User",
    "ForumPost",
    "DirectMessage",
    "ProfessionalQuery",
    "Report",
    "Document",
    "AuditLog",
]
