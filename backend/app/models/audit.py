"""
Audit log model.

Every sensitive admin/moderator action is recorded here.
Logs are append-only (never update or delete).
Retention: 7 years (Israeli legal requirement).

Only ADMIN role can read audit logs.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import AuditAction
from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # The admin/moderator who performed the action
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)  # no FK – logs outlive users

    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False)

    # The entity that was affected (e.g. "User", "ForumPost")
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # Extra context stored as JSON (e.g. {"reason": "...", "new_status": "..."})
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # The IP address of the actor (encrypted)
    ip_address: Mapped[str | None] = mapped_column(String(256), nullable=True)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    actor: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        primaryjoin="foreign(AuditLog.actor_id) == User.id",
        viewonly=True,
        back_populates="audit_logs",
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action} actor={self.actor_id}>"
