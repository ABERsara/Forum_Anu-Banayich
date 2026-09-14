"""
UserRestriction model — the automatic protection measures of spec §7.2,
and §5.3's מה"ק, as rows rather than as flags on the user.

A restriction is an *event with an end*: it was applied at a moment, by a
rule, on a count of reports, and it stops on its own at `expires_at`. Three
things follow from storing it that way instead of as `is_restricted` +
`restricted_until` columns on `users`:

  * expiry needs no job. "Is she restricted right now" is a query against
    `expires_at`, so a restriction that has run out is simply not found —
    there is no scheduled task that has to run for a member to get her
    messaging back, and none that can fail to.
  * the history survives the restriction. A moderator opening the dashboard
    after the fact can still see that a restriction was applied, when, and
    on how many upheld reports (§7.3 asks the user card for exactly these
    counts); a flag that was cleared says none of it.
  * a second rule is a second row. Both directions of ABF-116 — the sender
    repeatedly reported, and the member whose reports keep being dismissed —
    are the same shape, and neither can overwrite the other's state.

Rows are never mutated after they are written. Re-crossing a threshold while
a restriction is still running extends nothing and writes nothing (see
restriction_service.apply_restriction); once it has lapsed, crossing again
writes a new row beside the old one.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import RestrictionType
from app.db.base import Base


class UserRestriction(Base):
    __tablename__ = "user_restrictions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # ------------------------------------------------------------------
    # Who is restricted, and from what
    # ------------------------------------------------------------------
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    restriction_type: Mapped[RestrictionType] = mapped_column(
        Enum(RestrictionType), nullable=False
    )

    # ------------------------------------------------------------------
    # Until when
    # ------------------------------------------------------------------
    #: Naive UTC, like every other timestamp in this schema (see
    #: report_service.decide_report on why): the `created_at` beside it is
    #: filled by the database's own naive now(), and an aware value here
    #: would make the two incomparable.
    #:
    #: NOT NULL on purpose. The acceptance criterion is that a restriction
    #: has an end date, and a nullable column is an invitation to write a
    #: permanent one — which is a suspension, and a suspension is a human's
    #: decision (§7.2 "עיון בהשעיה"), not a threshold's.
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # ------------------------------------------------------------------
    # Why — the evidence, so the dashboard can show it without recounting
    # ------------------------------------------------------------------
    #: How many decided reports were inside the window when this was applied.
    report_count: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The window that count was taken over, in days. Stored rather than read
    #: from settings at display time: the thresholds are tunable (that is the
    #: ticket's own note), and a restriction has to keep saying what it was
    #: actually applied for after someone tunes them.
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The report whose decision crossed the threshold. Nullable because a
    #: report can be deleted or anonymized (§9.4) long before the seven years
    #: an audit entry is kept — losing the pointer must not lose the row.
    triggered_by_report_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("reports.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="restrictions", foreign_keys=[user_id]
    )

    __table_args__ = (
        # Every read is "the live restrictions of this kind for this user",
        # and it runs on the private-message send path — the one request in
        # the app a member makes over and over in a sitting.
        Index(
            "ix_user_restrictions_user_type_expires",
            "user_id",
            "restriction_type",
            "expires_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<UserRestriction user={self.user_id} "
            f"type={self.restriction_type} until={self.expires_at}>"
        )
