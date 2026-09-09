"""
CLI entry point for the scheduled 3-year private-message retention job
(spec §5.3/§9.4, ABF-117).

Run manually:
    cd backend && python -m scripts.purge_expired_messages

Run on a schedule: .github/workflows/message-retention.yml — the first real
scheduler wired up in this project. user_service.escalate_overdue_registrations
(ABF-76) is the same kind of plain, scheduler-agnostic function but nothing
has ever actually called it outside tests; this script is what that one is
still missing.

A thin wrapper only — purge_expired_direct_messages() is what any test
exercises directly. This script exists solely to own a DB session outside
the FastAPI request lifecycle, since app.db.session.SessionLocal is
otherwise reserved for get_db() (see that module's own docstring).
"""

import logging

from app.db.session import SessionLocal
from app.services.retention_service import purge_expired_direct_messages

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    db = SessionLocal()
    try:
        deleted_ids = purge_expired_direct_messages(db)
    finally:
        db.close()
    logger.info("Purged %d expired direct message(s).", len(deleted_ids))


if __name__ == "__main__":
    main()
