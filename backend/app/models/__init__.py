"""
Import all models here so that SQLAlchemy and Alembic can discover them.

When you create a new model file, add it to this list.
"""

from app.models.agent import AgentConversation, AgentMessage
from app.models.agent_knowledge import AgentKnowledgeChunk
from app.models.audit import AuditLog
from app.models.document import Document
from app.models.forum import DirectMessage, ForumPost
from app.models.like import Like
from app.models.professional import ProfessionalQuery
from app.models.report import Report
from app.models.user import User

__all__ = [
    "User",
    "ForumPost",
    "DirectMessage",
    "ProfessionalQuery",
    "Report",
    "Like",
    "Document",
    "AuditLog",
    "AgentConversation",
    "AgentMessage",
    "AgentKnowledgeChunk",
]
