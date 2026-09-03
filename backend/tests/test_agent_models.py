"""
Smoke tests for the agent ORM models that this ticket delivers but no
service/endpoint touches yet: AgentKnowledgeEntry, AgentConversation,
AgentMessage. Pins the column definitions nothing else exercises — the
AgentMessageRole enum round-trip, the key_version default, the timestamp
server defaults, and nullability of the optional provenance fields.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.constants import (
    AgentMessageRole,
    GroupVisibility,
    ProfessionalDomain,
    SectorVisibility,
)
from app.models.agent import (
    AgentConversation,
    AgentDomain,
    AgentKnowledgeEntry,
    AgentMessage,
)
from app.models.user import User


def _domain(db_session: Session) -> AgentDomain:
    domain = AgentDomain(
        name="זכויות משפחות חד-הוריות",
        description="מידע כללי",
        group_visibility=GroupVisibility.ALL,
        sector_visibility=SectorVisibility.ALL,
        professional_domain=ProfessionalDomain.SOCIAL_WORKER,
    )
    db_session.add(domain)
    db_session.commit()
    return domain


def _user(db_session: Session, email: str = "dev@example.com") -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Dev",
        last_name="Team",
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_agent_domain_is_active_defaults_true(db_session: Session) -> None:
    domain = _domain(db_session)
    db_session.refresh(domain)

    assert domain.is_active is True
    assert isinstance(domain.created_at, datetime)


class TestAgentKnowledgeEntry:
    def test_round_trip_with_optional_source_fields_omitted(
        self, db_session: Session
    ) -> None:
        domain = _domain(db_session)
        author = _user(db_session)
        entry = AgentKnowledgeEntry(
            domain_id=domain.id,
            title="קצבת ילדים",
            content="פרטים על הקצבה",
            updated_by=author.id,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        assert entry.source_name is None
        assert entry.source_url is None
        assert isinstance(entry.created_at, datetime)
        assert isinstance(entry.updated_at, datetime)

    def test_stores_provenance_when_provided(self, db_session: Session) -> None:
        domain = _domain(db_session)
        author = _user(db_session)
        entry = AgentKnowledgeEntry(
            domain_id=domain.id,
            title="הטבות מס",
            content="...",
            source_name="כל זכות",
            source_url="https://www.kolzchut.org.il/he/example",
            updated_by=author.id,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        assert entry.source_name == "כל זכות"
        assert entry.source_url.startswith("https://")


class TestAgentConversationAndMessages:
    def test_conversation_and_messages_round_trip(self, db_session: Session) -> None:
        domain = _domain(db_session)
        member = _user(db_session, "member@example.com")

        conversation = AgentConversation(user_id=member.id, domain_id=domain.id)
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)

        assert isinstance(conversation.started_at, datetime)
        assert isinstance(conversation.last_message_at, datetime)

        question = AgentMessage(
            conversation_id=conversation.id,
            role=AgentMessageRole.USER,
            content="האם מגיע לי סיוע בדיור?",
        )
        answer = AgentMessage(
            conversation_id=conversation.id,
            role=AgentMessageRole.AGENT,
            content="על פי בסיס הידע...",
        )
        db_session.add_all([question, answer])
        db_session.commit()
        db_session.refresh(question)
        db_session.refresh(answer)

        # the enum round-trips to the right member, not a raw string
        assert question.role is AgentMessageRole.USER
        assert answer.role is AgentMessageRole.AGENT
        # key_version default applied by the ORM
        assert question.key_version == 1
        assert answer.key_version == 1
        assert isinstance(question.created_at, datetime)

    def test_messages_are_scoped_to_their_conversation(
        self, db_session: Session
    ) -> None:
        domain = _domain(db_session)
        member = _user(db_session, "member2@example.com")
        conversation = AgentConversation(user_id=member.id, domain_id=domain.id)
        db_session.add(conversation)
        db_session.commit()
        db_session.add(
            AgentMessage(
                conversation_id=conversation.id,
                role=AgentMessageRole.USER,
                content="שאלה",
            )
        )
        db_session.commit()

        rows = (
            db_session.query(AgentMessage)
            .filter(AgentMessage.conversation_id == conversation.id)
            .all()
        )

        assert [m.content for m in rows] == ["שאלה"]
