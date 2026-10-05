"""
A professional's Google Calendar authorisation (ABF-156).

The Google sign-in the platform already had (`POST /auth/google`) proves
*identity* and nothing else — it verifies a Firebase ID token and stops
there. Creating a calendar event is a different grant, with its own consent
screen, so a professional who has logged in with Google a hundred times
still has to authorise the calendar scope once before her first meeting.

Its own table rather than columns on `users`: this row holds a long-lived
secret, and the users row is loaded on nearly every request in the system
and reached through a dozen relationships. Keeping the secret out of it
means it only ever leaves the database when this module asks for it, and
forgetting a grant Google no longer honours is one DELETE that touches
nothing else.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GoogleCalendarCredential(Base):
    __tablename__ = "google_calendar_credentials"

    #: One authorisation per user, so the user id *is* the key — re-authorising
    #: replaces the row rather than accumulating rows nobody can tell apart.
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), primary_key=True
    )

    #: Encrypted with app/core/encryption.py (AES-256-GCM), never stored raw.
    #: That module is named for private messages because they were its first
    #: caller; the primitive is general, and a second encryption key would be
    #: one more secret to rotate and lose without adding real separation.
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    #: Which MESSAGE_ENCRYPTION_KEY epoch encrypted `refresh_token`, same
    #: mechanism as DirectMessage.key_version.
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    #: The scopes Google actually granted, which is not always what was
    #: requested — the consent screen lets a user tick fewer. Stored so the
    #: refusal can say "the calendar permission was not granted" instead of
    #: surfacing later as a 403 from Google in the middle of scheduling.
    scope: Mapped[str] = mapped_column(String(512), nullable=False)

    #: No access token here on purpose. It lives an hour, scheduling a meeting
    #: is a rare action, and one refresh call before each one is cheaper than
    #: a second secret at rest that has to be encrypted, expired and rotated.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", foreign_keys=[user_id]
    )

    def __repr__(self) -> str:
        return f"<GoogleCalendarCredential user={self.user_id}>"
