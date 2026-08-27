"""
Integration tests for GET /admin/registrations/{id} — the single registration
an admin opens from the pending queue before deciding on it.
"""

from datetime import date, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.constants import AccountStatus, DocumentType, Sector, UserRole, UserType
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.document import Document
from app.models.user import User

BASE = "/api/v1/admin/registrations"

#: Fixed timestamps, so "oldest upload first" is a real assertion and not a
#: race between rows written in the same second.
FILED_FIRST = datetime(2026, 6, 30, 9, 0, 0)
FILED_SECOND = datetime(2026, 6, 30, 9, 5, 0)
FILED_THIRD = datetime(2026, 6, 30, 9, 10, 0)


def _make_user(
    db_session: Session,
    role: UserRole,
    email: str,
    **overrides: Any,
) -> User:
    columns: dict[str, Any] = {
        "email": email,
        "password_hash": "hashed",
        "first_name": "Test",
        "last_name": "User",
        "role": role,
        "account_status": AccountStatus.ACTIVE,
    }
    columns.update(overrides)

    user = User(**columns)
    db_session.add(user)
    db_session.commit()
    return user


def _make_applicant(db_session: Session, **overrides: Any) -> User:
    """A registration waiting for its two admins (SPEC §8.2)."""
    columns: dict[str, Any] = {
        "first_name": "שרה",
        "last_name": "לוי",
        "phone": "0501234567",
        "birth_date": date(1985, 3, 15),
        "id_number": "123456789",
        "user_type": UserType.WIDOW,
        "sector": Sector.SEPHARDIC,
        "account_status": AccountStatus.PENDING_APPROVAL,
    }
    columns.update(overrides)
    email = columns.pop("email", "sara.levi@example.com")

    return _make_user(db_session, UserRole.USER, email, **columns)


def _make_document(
    db_session: Session,
    applicant: User,
    doc_type: DocumentType,
    uploaded_at: datetime,
    **kwargs: Any,
) -> Document:
    document = Document(
        user_id=applicant.id,
        doc_type=doc_type,
        storage_url="s3://anu-banayich/private/enc/abc123",
        content_hash="a" * 64,
        uploaded_at=uploaded_at,
        **kwargs,
    )
    db_session.add(document)
    db_session.commit()
    return document


@pytest.fixture
def as_user():
    """Override get_current_user and get_current_active_user to return the given user."""

    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
def admin(db_session: Session) -> User:
    return _make_user(db_session, UserRole.ADMIN, "admin@example.com")


class TestTheApplicantProfile:
    async def test_returns_the_details_the_decision_rests_on(
        self, client, db_session, as_user, admin
    ) -> None:
        """The acceptance scenario: who filed the request, and as what."""
        applicant = _make_applicant(db_session)
        as_user(admin)

        response = await client.get(f"{BASE}/{applicant.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == applicant.id
        assert body["first_name"] == "שרה"
        assert body["last_name"] == "לוי"
        assert body["user_type"] == UserType.WIDOW
        assert body["sector"] == Sector.SEPHARDIC
        assert body["id_number"] == "123456789"
        assert body["birth_date"] == "1985-03-15"
        assert body["account_status"] == AccountStatus.PENDING_APPROVAL
        assert body["created_at"]

    async def test_carries_every_field_the_queue_row_carries(
        self, client, db_session, as_user, admin
    ) -> None:
        """
        Opening a row must never show *less* than the row itself, so the detail
        view is a superset of the queue entry, field for field.
        """
        _make_applicant(db_session)
        as_user(admin)
        [row] = (await client.get(BASE)).json()

        detail = (await client.get(f"{BASE}/{row['id']}")).json()

        assert row.items() <= detail.items()

    async def test_shows_how_far_the_double_approval_got(
        self, client, db_session, as_user, admin
    ) -> None:
        """
        Half-approved is exactly when the second admin needs the file open, so
        it is readable — and it says who already approved.
        """
        applicant = _make_applicant(
            db_session,
            account_status=AccountStatus.PARTIALLY_APPROVED,
            first_approver_id=admin.id,
        )
        as_user(admin)

        response = await client.get(f"{BASE}/{applicant.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["account_status"] == AccountStatus.PARTIALLY_APPROVED
        assert body["first_approver_id"] == admin.id
        assert body["second_approver_id"] is None


class TestTheUploadedDocuments:
    async def test_lists_what_was_uploaded_and_when(
        self, client, db_session, as_user, admin
    ) -> None:
        applicant = _make_applicant(db_session)
        _make_document(
            db_session,
            applicant,
            DocumentType.ID_CARD,
            FILED_FIRST,
            expires_on=date(2030, 1, 1),
        )
        as_user(admin)

        response = await client.get(f"{BASE}/{applicant.id}")

        [document] = response.json()["documents"]
        assert document["doc_type"] == DocumentType.ID_CARD
        assert document["uploaded_at"] == FILED_FIRST.isoformat()
        assert document["expires_on"] == "2030-01-01"

    async def test_lists_them_oldest_upload_first(
        self, client, db_session, as_user, admin
    ) -> None:
        applicant = _make_applicant(db_session)
        _make_document(db_session, applicant, DocumentType.PASSPORT, FILED_THIRD)
        _make_document(db_session, applicant, DocumentType.SELFIE, FILED_FIRST)
        _make_document(
            db_session, applicant, DocumentType.DEATH_CERTIFICATE, FILED_SECOND
        )
        as_user(admin)

        response = await client.get(f"{BASE}/{applicant.id}")

        assert [d["doc_type"] for d in response.json()["documents"]] == [
            DocumentType.SELFIE,
            DocumentType.DEATH_CERTIFICATE,
            DocumentType.PASSPORT,
        ]

    async def test_a_document_without_an_expiry_reports_none(
        self, client, db_session, as_user, admin
    ) -> None:
        applicant = _make_applicant(db_session)
        _make_document(
            db_session, applicant, DocumentType.DEATH_CERTIFICATE, FILED_FIRST
        )
        as_user(admin)

        response = await client.get(f"{BASE}/{applicant.id}")

        assert response.json()["documents"][0]["expires_on"] is None

    async def test_a_registration_with_no_documents_returns_an_empty_list(
        self, client, db_session, as_user, admin
    ) -> None:
        """An incomplete request is itself a finding — never a missing key."""
        applicant = _make_applicant(db_session)
        as_user(admin)

        response = await client.get(f"{BASE}/{applicant.id}")

        assert response.status_code == 200
        assert response.json()["documents"] == []

    async def test_never_exposes_the_storage_path_or_the_content_hash(
        self, client, db_session, as_user, admin
    ) -> None:
        """
        Metadata only until presigned URLs land (SPEC §9.1): the bucket path is
        not a link anyone can open, and the hash is a fingerprint of a document
        the admin decides nothing from.
        """
        applicant = _make_applicant(db_session)
        _make_document(db_session, applicant, DocumentType.SELFIE, FILED_FIRST)
        as_user(admin)

        response = await client.get(f"{BASE}/{applicant.id}")

        [document] = response.json()["documents"]
        assert "storage_url" not in document
        assert "content_hash" not in document
        assert "anu-banayich" not in response.text

    async def test_only_the_applicant_s_own_documents_are_listed(
        self, client, db_session, as_user, admin
    ) -> None:
        applicant = _make_applicant(db_session)
        someone_else = _make_applicant(db_session, email="other@example.com")
        _make_document(db_session, applicant, DocumentType.SELFIE, FILED_FIRST)
        _make_document(db_session, someone_else, DocumentType.PASSPORT, FILED_SECOND)
        as_user(admin)

        response = await client.get(f"{BASE}/{applicant.id}")

        assert [d["doc_type"] for d in response.json()["documents"]] == [
            DocumentType.SELFIE
        ]


class TestWhoAndWhatMayBeOpened:
    async def test_unknown_user_returns_404(self, client, as_user, admin) -> None:
        as_user(admin)

        response = await client.get(f"{BASE}/does-not-exist")

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "settled_status",
        [
            pytest.param(AccountStatus.ACTIVE, id="already_approved"),
            pytest.param(AccountStatus.REJECTED, id="already_rejected"),
            pytest.param(AccountStatus.SUSPENDED, id="suspended"),
            pytest.param(AccountStatus.CANCELLED, id="cancelled"),
            pytest.param(AccountStatus.PENDING_OTP, id="never_reached_the_queue"),
        ],
    )
    async def test_a_registration_that_is_not_waiting_returns_403(
        self, client, db_session, as_user, admin, settled_status: AccountStatus
    ) -> None:
        """
        The row exists — what is refused is reviewing a request that is no
        longer open, so a stale screen cannot decide it a second time.
        """
        applicant = _make_applicant(db_session, account_status=settled_status)
        as_user(admin)

        response = await client.get(f"{BASE}/{applicant.id}")

        assert response.status_code == 403

    async def test_the_refusal_does_not_leak_the_applicant(
        self, client, db_session, as_user, admin
    ) -> None:
        applicant = _make_applicant(db_session, account_status=AccountStatus.REJECTED)
        as_user(admin)

        response = await client.get(f"{BASE}/{applicant.id}")

        assert "123456789" not in response.text
        assert "sara.levi@example.com" not in response.text

    async def test_requires_authentication(self, client, db_session) -> None:
        applicant = _make_applicant(db_session)

        response = await client.get(f"{BASE}/{applicant.id}")

        assert response.status_code == 401

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(UserRole.USER, id="member"),
            pytest.param(UserRole.MODERATOR, id="moderator"),
            pytest.param(UserRole.PROFESSIONAL, id="professional"),
        ],
    )
    async def test_forbidden_for_non_admin_roles(
        self, client, db_session, as_user, role: UserRole
    ) -> None:
        applicant = _make_applicant(db_session)
        as_user(_make_user(db_session, role, f"{role}@example.com"))

        response = await client.get(f"{BASE}/{applicant.id}")

        assert response.status_code == 403


class TestReviewingChangesNothing:
    async def test_opening_a_registration_leaves_it_in_the_queue(
        self, client, db_session, as_user, admin
    ) -> None:
        applicant = _make_applicant(db_session)
        as_user(admin)

        await client.get(f"{BASE}/{applicant.id}")

        db_session.refresh(applicant)
        assert applicant.account_status == AccountStatus.PENDING_APPROVAL
        assert applicant.first_approver_id is None
        assert [row["id"] for row in (await client.get(BASE)).json()] == [applicant.id]
