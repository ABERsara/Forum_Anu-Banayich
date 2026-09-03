"""
Professional query model.

A ProfessionalQuery is a question asked by a USER to a PROFESSIONAL.

is_public=True  → visible to all members of the asker's group/sector after answered
is_public=False → visible only to the asker and the professional
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ProfessionalDomain, QueryStatus, Sector, UserType
from app.db.base import Base


class ProfessionalQuery(Base):
    __tablename__ = "professional_queries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # ------------------------------------------------------------------
    # Participants
    # ------------------------------------------------------------------
    asker_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    # If None → general question to the whole domain, not a specific professional
    professional_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    # Used when professional_id is None – question targets all professionals in this domain
    domain: Mapped[ProfessionalDomain | None] = mapped_column(
        Enum(ProfessionalDomain), nullable=True
    )

    # ------------------------------------------------------------------
    # Asker's group/sector cell, frozen at creation time (see create_query()).
    # Unlike ForumPost's GroupVisibility/SectorVisibility there is no "all"
    # member here: a professional question always belongs to exactly one
    # cell. Nullable because historical rows backfilled from a since-cleared
    # asker profile may have no source value to copy — such a row simply
    # never appears in the public feed.
    # ------------------------------------------------------------------
    asker_user_type: Mapped[UserType | None] = mapped_column(
        Enum(UserType), nullable=True
    )
    asker_sector: Mapped[Sector | None] = mapped_column(Enum(Sector), nullable=True)

    # ------------------------------------------------------------------
    # Content (stored encrypted)
    # ------------------------------------------------------------------
    content: Mapped[str] = mapped_column(Text, nullable=False)  # encrypted
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted

    # ------------------------------------------------------------------
    # Visibility & status
    # ------------------------------------------------------------------
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[QueryStatus] = mapped_column(
        Enum(QueryStatus), nullable=False, default=QueryStatus.OPEN
    )
    is_featured: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # "מועדפת" by asker

    # ------------------------------------------------------------------
    # Privacy: professional sees only this alias (e.g. "אלמנה – ספרדי")
    # unless the asker explicitly chooses to reveal their name
    # ------------------------------------------------------------------
    show_real_name: Mapped[bool] = mapped_column(Boolean, default=False)

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    asker: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="professional_queries", foreign_keys=[asker_id]
    )
    professional: Mapped["User | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", foreign_keys=[professional_id]
    )
    likes: Mapped[list["Like"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Like",
        primaryjoin="and_(Like.target_id == ProfessionalQuery.id, Like.target_type == 'professional_query')",
        foreign_keys="Like.target_id",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<ProfessionalQuery id={self.id} status={self.status}>"
