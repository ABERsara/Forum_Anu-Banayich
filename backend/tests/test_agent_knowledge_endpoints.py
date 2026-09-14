"""
Integration tests for the knowledge base endpoints.

POST   /agents/{domain_id}/knowledge-entries
PATCH  /agents/{domain_id}/knowledge-entries/{entry_id}
DELETE /agents/{domain_id}/knowledge-entries/{entry_id}

What these are about is who may write to a knowledge base, and what the API
tells someone who may not. Indexing is stubbed throughout: it is tested against
a real pgvector database in test_rag_service.py, and letting it run here would
put a Gemini call inside an authorization test.

The two refusals are deliberately different, and both are asserted:
404 for a domain or an entry the caller cannot see, 403 only once the thing is
known to exist and to not be theirs. A 403 on a domain id that does not exist
would answer a question about the catalog that was never asked.
"""

import pytest
from sqlalchemy.orm import Session

from app.core.constants import ProfessionalDomain, Sector, UserRole, UserType
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.agent import AgentKnowledgeEntry
from app.models.user import User
from app.services import rag_service

BASE = "/api/v1/agents"


def _entries_url(domain_id: str) -> str:
    return f"{BASE}/{domain_id}/knowledge-entries"


@pytest.fixture
def as_user():
    """Override get_current_user and get_current_active_user to return the given user."""

    def _apply(user: User) -> None:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
def indexed(monkeypatch):
    """Record which entries were sent for indexing, without indexing them."""
    entry_ids: list[str] = []

    def _index_entry(db: Session, entry: AgentKnowledgeEntry) -> None:
        entry_ids.append(entry.id)

    monkeypatch.setattr(rag_service, "index_entry", _index_entry)
    return entry_ids


@pytest.fixture
def lawyer_domain(make_agent_domain):
    return make_agent_domain("זכויות", ProfessionalDomain.LAWYER)


@pytest.fixture
def lawyer(make_user):
    return make_user(
        "lawyer@example.com",
        role=UserRole.PROFESSIONAL,
        professional_domain=ProfessionalDomain.LAWYER,
    )


@pytest.fixture
def admin(make_user):
    return make_user("admin@example.com", role=UserRole.ADMIN)


def _add_entry(
    db_session: Session,
    domain_id: str,
    author: User,
    title: str = "ארנונה",
    content: str = "הנחה בארנונה למשפחה חד-הורית.",
) -> AgentKnowledgeEntry:
    entry = AgentKnowledgeEntry(
        domain_id=domain_id,
        title=title,
        content=content,
        updated_by=author.id,
    )
    db_session.add(entry)
    db_session.commit()
    return entry


VALID_BODY = {
    "title": "הנחה בארנונה",
    "content": "משפחה חד-הורית זכאית להנחה בארנונה.",
    "source_name": "אתר הרשות",
    "source_url": "https://example.gov.il/arnona",
}


class TestWhoMayWrite:
    async def test_an_admin_may_add_to_any_domain(
        self, client, as_user, admin, lawyer_domain, indexed
    ) -> None:
        as_user(admin)

        response = await client.post(_entries_url(lawyer_domain.id), json=VALID_BODY)

        assert response.status_code == 201
        assert response.json()["title"] == VALID_BODY["title"]

    async def test_a_professional_may_add_to_a_domain_of_their_own_discipline(
        self, client, as_user, lawyer, lawyer_domain, indexed
    ) -> None:
        as_user(lawyer)

        response = await client.post(_entries_url(lawyer_domain.id), json=VALID_BODY)

        assert response.status_code == 201

    async def test_a_professional_of_another_discipline_is_refused(
        self, client, as_user, make_user, lawyer_domain, indexed
    ) -> None:
        # A doctor editing the legal-rights agent is the case the discipline
        # check exists for.
        doctor = make_user(
            "doctor@example.com",
            role=UserRole.PROFESSIONAL,
            professional_domain=ProfessionalDomain.MEDICINE,
        )
        as_user(doctor)

        response = await client.post(_entries_url(lawyer_domain.id), json=VALID_BODY)

        assert response.status_code == 403

    async def test_a_professional_with_no_discipline_set_is_refused(
        self, client, as_user, make_user, lawyer_domain, indexed
    ) -> None:
        # professional_domain is nullable. "Not set" must not match anything.
        unassigned = make_user("nobody@example.com", role=UserRole.PROFESSIONAL)
        as_user(unassigned)

        response = await client.post(_entries_url(lawyer_domain.id), json=VALID_BODY)

        assert response.status_code == 403

    @pytest.mark.parametrize("role", [UserRole.USER, UserRole.MODERATOR])
    async def test_a_member_or_moderator_is_refused(
        self, client, as_user, make_user, lawyer_domain, indexed, role: UserRole
    ) -> None:
        actor = make_user(
            f"{role.value}@example.com",
            role=role,
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        as_user(actor)

        response = await client.post(_entries_url(lawyer_domain.id), json=VALID_BODY)

        assert response.status_code == 403

    async def test_a_refused_request_writes_nothing(
        self, client, as_user, make_user, lawyer_domain, db_session, indexed
    ) -> None:
        member = make_user(
            "member@example.com", user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        as_user(member)

        await client.post(_entries_url(lawyer_domain.id), json=VALID_BODY)

        assert db_session.query(AgentKnowledgeEntry).count() == 0

    async def test_an_unauthenticated_request_is_401(
        self, client, lawyer_domain
    ) -> None:
        response = await client.post(_entries_url(lawyer_domain.id), json=VALID_BODY)
        assert response.status_code == 401


class TestUnknownDomain:
    async def test_a_domain_that_does_not_exist_is_404_not_403(
        self, client, as_user, lawyer, indexed
    ) -> None:
        # Sara's IDOR point: 403 here would confirm the id space to anyone
        # holding an editor's account.
        as_user(lawyer)

        response = await client.post(
            _entries_url("00000000-0000-0000-0000-000000000000"), json=VALID_BODY
        )

        assert response.status_code == 404

    async def test_a_member_is_still_refused_before_the_domain_is_looked_up(
        self, client, as_user, make_user, indexed
    ) -> None:
        # The role gate runs first, so an ordinary member cannot use these
        # routes to probe which domain ids exist.
        member = make_user(
            "member@example.com", user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        as_user(member)

        response = await client.post(
            _entries_url("00000000-0000-0000-0000-000000000000"), json=VALID_BODY
        )

        assert response.status_code == 403


class TestCreate:
    async def test_the_entry_is_stored_against_the_domain_in_the_path(
        self, client, as_user, lawyer, lawyer_domain, db_session, indexed
    ) -> None:
        as_user(lawyer)

        body = (
            await client.post(_entries_url(lawyer_domain.id), json=VALID_BODY)
        ).json()

        stored = db_session.get(AgentKnowledgeEntry, body["id"])
        assert stored is not None
        assert stored.domain_id == lawyer_domain.id

    async def test_the_author_is_the_authenticated_caller(
        self, client, as_user, lawyer, lawyer_domain, indexed
    ) -> None:
        # updated_by is not in the request schema — a caller cannot claim to be
        # someone else by putting it in the body.
        as_user(lawyer)

        body = (
            await client.post(
                _entries_url(lawyer_domain.id),
                json={**VALID_BODY, "updated_by": "someone-else"},
            )
        ).json()

        assert body["updated_by"] == lawyer.id

    async def test_a_new_entry_is_indexed(
        self, client, as_user, lawyer, lawyer_domain, indexed
    ) -> None:
        as_user(lawyer)

        body = (
            await client.post(_entries_url(lawyer_domain.id), json=VALID_BODY)
        ).json()

        assert indexed == [body["id"]]

    async def test_an_entry_survives_an_indexing_failure(
        self, client, as_user, lawyer, lawyer_domain, db_session, monkeypatch
    ) -> None:
        # The professional's work is not thrown away because Google was
        # unreachable — the entry saves, it is just not retrievable yet.
        def _fail(db: Session, entry: AgentKnowledgeEntry) -> None:
            raise rag_service.EmbeddingError("Gemini is unreachable")

        monkeypatch.setattr(rag_service, "index_entry", _fail)
        as_user(lawyer)

        response = await client.post(_entries_url(lawyer_domain.id), json=VALID_BODY)

        assert response.status_code == 201
        assert db_session.query(AgentKnowledgeEntry).count() == 1

    async def test_empty_content_is_rejected(
        self, client, as_user, lawyer, lawyer_domain, indexed
    ) -> None:
        as_user(lawyer)

        response = await client.post(
            _entries_url(lawyer_domain.id), json={**VALID_BODY, "content": ""}
        )

        assert response.status_code == 422


class TestUpdate:
    async def test_a_partial_update_leaves_the_other_fields_alone(
        self, client, as_user, lawyer, lawyer_domain, db_session, indexed
    ) -> None:
        entry = _add_entry(db_session, lawyer_domain.id, lawyer)
        as_user(lawyer)

        response = await client.patch(
            f"{_entries_url(lawyer_domain.id)}/{entry.id}",
            json={"title": "כותרת מתוקנת"},
        )

        assert response.status_code == 200
        assert response.json()["title"] == "כותרת מתוקנת"
        assert response.json()["content"] == "הנחה בארנונה למשפחה חד-הורית."

    @pytest.mark.parametrize("field", ["source_name", "source_url"])
    async def test_an_update_to_a_source_field_alone_does_not_re_index(
        self, client, as_user, lawyer, lawyer_domain, db_session, indexed, field: str
    ) -> None:
        # Nothing an embedding is built from changed, so re-indexing here would
        # spend a paid round trip rebuilding vectors identical to the ones
        # already stored.
        entry = _add_entry(db_session, lawyer_domain.id, lawyer)
        as_user(lawyer)

        await client.patch(
            f"{_entries_url(lawyer_domain.id)}/{entry.id}",
            json={field: "מקור מתוקן"},
        )

        assert indexed == []

    async def test_an_update_that_sends_the_title_re_indexes(
        self, client, as_user, lawyer, lawyer_domain, db_session, indexed
    ) -> None:
        # index_entry() embeds each chunk with the title in front of it, so a
        # renamed entry whose chunks were left alone would go on being searched
        # for under the name its author just replaced.
        entry = _add_entry(db_session, lawyer_domain.id, lawyer)
        as_user(lawyer)

        await client.patch(
            f"{_entries_url(lawyer_domain.id)}/{entry.id}",
            json={"title": "כותרת מתוקנת"},
        )

        assert indexed == [entry.id]

    async def test_an_update_that_sends_content_re_indexes(
        self, client, as_user, lawyer, lawyer_domain, db_session, indexed
    ) -> None:
        entry = _add_entry(db_session, lawyer_domain.id, lawyer)
        as_user(lawyer)

        await client.patch(
            f"{_entries_url(lawyer_domain.id)}/{entry.id}",
            json={"content": "תוכן מעודכן."},
        )

        assert indexed == [entry.id]

    async def test_the_editor_becomes_the_last_author(
        self, client, as_user, admin, lawyer, lawyer_domain, db_session, indexed
    ) -> None:
        entry = _add_entry(db_session, lawyer_domain.id, lawyer)
        as_user(admin)

        body = (
            await client.patch(
                f"{_entries_url(lawyer_domain.id)}/{entry.id}",
                json={"title": "תוקן על ידי מנהל"},
            )
        ).json()

        assert body["updated_by"] == admin.id

    async def test_clearing_the_content_is_rejected(
        self, client, as_user, lawyer, lawyer_domain, db_session, indexed
    ) -> None:
        # A NOT NULL column, and an entry with no content is not a state the
        # knowledge base has. Omitting the field is how you leave it alone.
        entry = _add_entry(db_session, lawyer_domain.id, lawyer)
        as_user(lawyer)

        response = await client.patch(
            f"{_entries_url(lawyer_domain.id)}/{entry.id}", json={"content": None}
        )

        assert response.status_code == 422

    async def test_an_edit_survives_an_indexing_failure(
        self, client, as_user, lawyer, lawyer_domain, db_session, monkeypatch
    ) -> None:
        # The PATCH counterpart of TestCreate's version. An edit that cannot be
        # indexed still has to be kept: the entry is left updated and merely
        # unretrievable, which the next edit fixes. Losing the correction
        # because Google was down would be the worse of the two failures.
        entry = _add_entry(db_session, lawyer_domain.id, lawyer)
        attempted = []

        def _fail(db: Session, entry: AgentKnowledgeEntry) -> None:
            attempted.append(entry.id)
            raise rag_service.EmbeddingError("Gemini is unreachable")

        monkeypatch.setattr(rag_service, "index_entry", _fail)
        as_user(lawyer)

        response = await client.patch(
            f"{_entries_url(lawyer_domain.id)}/{entry.id}",
            json={"content": "תוכן מעודכן"},
        )

        assert response.status_code == 200
        # Both halves matter: that a content edit does reach the indexer, and
        # that its failure does not reach the caller. Without the first, this
        # would pass just as well if re-indexing had quietly stopped happening.
        assert attempted == [entry.id]
        db_session.expire_all()
        saved = db_session.get(AgentKnowledgeEntry, entry.id)
        assert saved.content == "תוכן מעודכן"

    async def test_clearing_a_source_is_allowed(
        self, client, as_user, lawyer, lawyer_domain, db_session, indexed
    ) -> None:
        entry = _add_entry(db_session, lawyer_domain.id, lawyer)
        entry.source_url = "https://example.gov.il/wrong"
        db_session.commit()
        as_user(lawyer)

        body = (
            await client.patch(
                f"{_entries_url(lawyer_domain.id)}/{entry.id}",
                json={"source_url": None},
            )
        ).json()

        assert body["source_url"] is None


class TestDelete:
    async def test_deleting_returns_204_and_removes_the_entry(
        self, client, as_user, lawyer, lawyer_domain, db_session, indexed
    ) -> None:
        entry = _add_entry(db_session, lawyer_domain.id, lawyer)
        as_user(lawyer)

        response = await client.delete(f"{_entries_url(lawyer_domain.id)}/{entry.id}")

        assert response.status_code == 204
        assert db_session.query(AgentKnowledgeEntry).count() == 0

    async def test_a_professional_of_another_discipline_may_not_delete(
        self, client, as_user, make_user, lawyer, lawyer_domain, db_session, indexed
    ) -> None:
        entry = _add_entry(db_session, lawyer_domain.id, lawyer)
        doctor = make_user(
            "doctor@example.com",
            role=UserRole.PROFESSIONAL,
            professional_domain=ProfessionalDomain.MEDICINE,
        )
        as_user(doctor)

        response = await client.delete(f"{_entries_url(lawyer_domain.id)}/{entry.id}")

        assert response.status_code == 403
        assert db_session.query(AgentKnowledgeEntry).count() == 1


class TestAnEntryOfAnotherDomain:
    """Both ids are in the path, and only the domain one is authorized.

    Without a check that the entry belongs to that domain, a professional could
    pair their own domain_id — which passes the permission check — with an
    entry_id from a domain they have no rights over, and edit or delete it.
    """

    @pytest.fixture
    def foreign_entry(self, db_session, make_agent_domain, make_user):
        other_domain = make_agent_domain("בריאות", ProfessionalDomain.MEDICINE)
        doctor = make_user(
            "doctor@example.com",
            role=UserRole.PROFESSIONAL,
            professional_domain=ProfessionalDomain.MEDICINE,
        )
        return _add_entry(db_session, other_domain.id, doctor, title="חיסונים")

    async def test_updating_it_through_my_own_domain_is_404(
        self, client, as_user, lawyer, lawyer_domain, foreign_entry, indexed
    ) -> None:
        as_user(lawyer)

        response = await client.patch(
            f"{_entries_url(lawyer_domain.id)}/{foreign_entry.id}",
            json={"title": "נחטף"},
        )

        assert response.status_code == 404

    async def test_deleting_it_through_my_own_domain_is_404(
        self, client, as_user, lawyer, lawyer_domain, foreign_entry, db_session, indexed
    ) -> None:
        as_user(lawyer)

        response = await client.delete(
            f"{_entries_url(lawyer_domain.id)}/{foreign_entry.id}"
        )

        assert response.status_code == 404
        assert db_session.query(AgentKnowledgeEntry).count() == 1

    async def test_the_foreign_entry_is_untouched(
        self, client, as_user, lawyer, lawyer_domain, foreign_entry, db_session, indexed
    ) -> None:
        as_user(lawyer)

        await client.patch(
            f"{_entries_url(lawyer_domain.id)}/{foreign_entry.id}",
            json={"title": "נחטף"},
        )

        db_session.refresh(foreign_entry)
        assert foreign_entry.title == "חיסונים"

    async def test_an_entry_id_that_does_not_exist_is_404(
        self, client, as_user, lawyer, lawyer_domain, indexed
    ) -> None:
        as_user(lawyer)

        response = await client.delete(
            f"{_entries_url(lawyer_domain.id)}/00000000-0000-0000-0000-000000000000"
        )

        assert response.status_code == 404
