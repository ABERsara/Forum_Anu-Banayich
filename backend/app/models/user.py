"""
User model – the central entity of the system.

All four roles (USER, ADMIN, MODERATOR, PROFESSIONAL) live in this table.
Role-specific fields are nullable and only populated for the relevant role.

Columns marked # encrypted should be encrypted at the application layer
before being stored. See services/auth_service.py for the encryption helpers.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    AccountStatus,
    ProfessionalDomain,
    Sector,
    UserRole,
    UserType,
)
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    # ------------------------------------------------------------------
    # Primary key
    # ------------------------------------------------------------------
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # ------------------------------------------------------------------
    # Auth (all roles)
    # ------------------------------------------------------------------
    email: Mapped[str] = mapped_column(
        String(512), unique=True, nullable=False
    )  # encrypted
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), nullable=False, default=UserRole.USER
    )

    # ------------------------------------------------------------------
    # Basic identity (all roles)
    # ------------------------------------------------------------------
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # ------------------------------------------------------------------
    # USER role – bereavement identity
    # ------------------------------------------------------------------
    user_type: Mapped[UserType | None] = mapped_column(Enum(UserType), nullable=True)
    sector: Mapped[Sector | None] = mapped_column(Enum(Sector), nullable=True)
    id_number: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # encrypted
    phone: Mapped[str | None] = mapped_column(String(512), nullable=True)  # encrypted
    face_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ------------------------------------------------------------------
    # Registration lifecycle (USER role)
    # ------------------------------------------------------------------
    account_status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus),
        nullable=False,
        default=AccountStatus.PENDING_OTP,
    )
    otp_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_approver_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    second_approver_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------
    # MODERATOR role – which cells (group+sector) this moderator oversees
    # Stored as JSON: [{"group": "widower", "sector": "hasidic"}, ...]
    # ------------------------------------------------------------------
    moderator_cells: Mapped[list[dict[str, str]] | None] = mapped_column(
        JSON, nullable=True
    )
    alert_email: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # ------------------------------------------------------------------
    # SLA escalation tracking (registration lifecycle)
    # ------------------------------------------------------------------
    sla_escalation_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # ------------------------------------------------------------------
    # PROFESSIONAL role
    # ------------------------------------------------------------------
    professional_domain: Mapped[ProfessionalDomain | None] = mapped_column(
        Enum(ProfessionalDomain), nullable=True
    )
    # JSON lists of UserType values: ["widower", "widow"] or ["all"]
    professional_groups: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # JSON lists of Sector values: ["hasidic", "litvish"] or ["all"]
    professional_sectors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    professional_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active_professional: Mapped[bool] = mapped_column(Boolean, default=True)

    # ------------------------------------------------------------------
    # Suspension tracking
    # ------------------------------------------------------------------
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    suspended_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    documents: Mapped[list["Document"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Document", back_populates="user", cascade="all, delete-orphan"
    )
    forum_posts: Mapped[list["ForumPost"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ForumPost", back_populates="author", foreign_keys="ForumPost.author_id"
    )
    sent_messages: Mapped[list["DirectMessage"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "DirectMessage", back_populates="sender", foreign_keys="DirectMessage.sender_id"
    )
    received_messages: Mapped[list["DirectMessage"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "DirectMessage",
        back_populates="recipient",
        foreign_keys="DirectMessage.recipient_id",
    )
    professional_queries: Mapped[list["ProfessionalQuery"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ProfessionalQuery",
        back_populates="asker",
        foreign_keys="ProfessionalQuery.asker_id",
    )
    reports_filed: Mapped[list["Report"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Report", back_populates="reporter", foreign_keys="Report.reporter_id"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "AuditLog",
        primaryjoin="foreign(AuditLog.actor_id) == User.id",
        viewonly=True,
        back_populates="actor",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} role={self.role} email=***>"
