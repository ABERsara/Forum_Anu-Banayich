"""
Document model.

Users upload documents during registration:
  - death_certificate  (required)
  - selfie             (required)
  - id_card or passport (required, one of the two)

Documents are stored in S3/Blob Storage.
The URL stored here is the encrypted storage path.
Admin views them via time-limited presigned URLs (15 min).
After registration approval, documents are kept for 10 years.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DocumentType
from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    doc_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType), nullable=False)

    # Encrypted path in cloud storage (S3 key or Blob path)
    storage_url: Mapped[str] = mapped_column(String(1024), nullable=False)

    # SHA-256 hash of original file content (integrity check)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Optional expiry date (e.g. for ID cards that expire)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="documents"
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} type={self.doc_type} user={self.user_id}>"
