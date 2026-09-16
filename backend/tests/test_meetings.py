"""
Integration tests for the meetings surface (ABF-156).

Google is never called: google_meet_service.create_meeting() is replaced
wherever a meeting is expected to succeed, and the one test that does exercise
the real path is the one asserting what happens when no calendar is linked —
which fails before any HTTP call. test_google_meet_service.py covers that
module's own behaviour against fake responses.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.constants import (
    AccountStatus,
    AuditAction,
    GroupVisibility,
    PostStatus,
    PostType,
    ProfessionalDomain,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.forum import ForumPost
from app.models.meeting import Meeting
from app.models.user import User
from app.services import google_meet_service, meeting_service

BASE = "/api/v1/meetings"

MEET_LINK = "https://meet.google.com/abc-defg-hij"
EVENT_ID = "evt-1"


def _login_as(user: User) -> None:
    """Bypass real JWT auth, as in test_forum_endpoints.py."""
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_active_user] = lambda: user


def _professional(make_user, **kwargs) -> User:
    defaults = {
        "email": "pro@example.com",
        "role": UserRole.PROFESSIONAL,
        "account_status": AccountStatus.ACTIVE,
        "professional_domain": ProfessionalDomain.PSYCHOLOGIST,
        "professional_groups": [UserType.WIDOW.value],
        "professional_sectors": [Sector.HASIDIC.value],
    }
    return make_user(**{**defaults, **kwargs})


def _member(make_user, **kwargs) -> User:
    defaults = {
        "email": "member@example.com",
        "user_type": UserType.WIDOW,
        "sector": Sector.HASIDIC,
        "account_status": AccountStatus.ACTIVE,
    }
    return make_user(**{**defaults, **kwargs})


def _payload(**overrides) -> dict[str, object]:
    body: dict[str, object] = {
        "title": "מפגש תמיכה",
        "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "group_visibility": GroupVisibility.WIDOWS.value,
        "sector_visibility": SectorVisibility.HASIDIC.value,
    }
    body.update(overrides)
    return body


@pytest.fixture
def google_succeeds(monkeypatch):
    """Stand in for Google, and record what it was asked to create."""
    calls: list[dict[str, object]] = []

    def _create(db, creator, *, title, scheduled_at, duration_minutes):
        calls.append(
            {
                "creator_id": creator.id,
                "title": title,
                "scheduled_at": scheduled_at,
                "duration_minutes": duration_minutes,
            }
        )
        return MEET_LINK, EVENT_ID

    monkeypatch.setattr(google_meet_service, "create_meeting", _create)
    return calls


def _make_meeting(
    db_session,
    creator: User,
    *,
    group_visibility: GroupVisibility = GroupVisibility.WIDOWS,
    sector_visibility: SectorVisibility = SectorVisibility.HASIDIC,
    starts_in: timedelta = timedelta(days=1),
    duration_minutes: int = 60,
    announcement_status: PostStatus = PostStatus.VISIBLE,
) -> Meeting:
    """A meeting and its announcement, as meeting_service.create_meeting()
    writes them. The announcement is not optional: GET /meetings lists a
    meeting only while it is VISIBLE, so a meeting without one is a state the
    real code never produces and the list would never show."""
    meeting = Meeting(
        creator_id=creator.id,
        title="מפגש",
        scheduled_at=datetime.now(UTC).replace(tzinfo=None) + starts_in,
        duration_minutes=duration_minutes,
        meet_link=MEET_LINK,
        calendar_event_id=EVENT_ID,
        group_visibility=group_visibility,
        sector_visibility=sector_visibility,
    )
    db_session.add(meeting)
    db_session.add(
        ForumPost(
            author_id=creator.id,
            title="מפגש",
            content="מפגש",
            group_visibility=group_visibility,
            sector_visibility=sector_visibility,
            status=announcement_status,
            post_type=PostType.MEETING,
            meeting=meeting,
        )
    )
    db_session.commit()
    return meeting


def _announcement_of(db_session, meeting: Meeting) -> ForumPost:
    return db_session.query(ForumPost).filter_by(meeting_id=meeting.id).one()


class TestCreateMeeting:
    async def test_professional_gets_201_and_an_announcement(
        self, client, db_session, make_user, google_succeeds
    ):
        professional = _professional(make_user)
        _login_as(professional)

        r = await client.post(BASE, json=_payload())

        assert r.status_code == 201
        body = r.json()
        assert body["meet_link"] == MEET_LINK
        assert body["creator"]["id"] == professional.id

        meeting = db_session.query(Meeting).one()
        assert meeting.duration_minutes == 60
        assert meeting.calendar_event_id == EVENT_ID

        post = db_session.query(ForumPost).one()
        assert post.post_type == PostType.MEETING
        assert post.meeting_id == meeting.id
        assert post.author_id == professional.id
        assert post.status == PostStatus.VISIBLE
        # The announcement inherits the meeting's cell exactly — this is what
        # makes it visible to those members and to nobody else.
        assert post.group_visibility == GroupVisibility.WIDOWS
        assert post.sector_visibility == SectorVisibility.HASIDIC

    async def test_creation_is_audited(
        self, client, db_session, make_user, google_succeeds
    ):
        professional = _professional(make_user)
        _login_as(professional)

        r = await client.post(BASE, json=_payload())

        assert r.status_code == 201
        entry = db_session.query(AuditLog).one()
        assert entry.action == AuditAction.MEETING_CREATED
        assert entry.actor_id == professional.id
        assert entry.entity_id == r.json()["id"]

    @pytest.mark.parametrize(
        "role,extra",
        [
            (UserRole.USER, {"user_type": UserType.WIDOW, "sector": Sector.HASIDIC}),
            (UserRole.ADMIN, {}),
            (UserRole.MODERATOR, {}),
        ],
    )
    async def test_everyone_but_a_professional_gets_403(
        self, client, db_session, make_user, google_succeeds, role, extra
    ):
        user = make_user(
            email=f"{role.value}@example.com",
            role=role,
            account_status=AccountStatus.ACTIVE,
            **extra,
        )
        _login_as(user)

        r = await client.post(BASE, json=_payload())

        assert r.status_code == 403
        assert db_session.query(Meeting).count() == 0
        assert google_succeeds == []

    async def test_cell_outside_her_assignment_is_403(
        self, client, db_session, make_user, google_succeeds
    ):
        # Assigned to hasidic widows; asking to convene litvish widows.
        professional = _professional(make_user)
        _login_as(professional)

        r = await client.post(
            BASE, json=_payload(sector_visibility=SectorVisibility.LITVISH.value)
        )

        assert r.status_code == 403
        assert db_session.query(Meeting).count() == 0
        # Nothing was created at Google either: the refusal comes before the
        # event, not after it.
        assert google_succeeds == []

    async def test_all_in_her_assignment_is_the_wildcard_it_is_elsewhere(
        self, client, db_session, make_user, google_succeeds
    ):
        professional = _professional(
            make_user, professional_groups=["all"], professional_sectors=["all"]
        )
        _login_as(professional)

        r = await client.post(
            BASE, json=_payload(group_visibility=GroupVisibility.ORPHANS_MALE.value)
        )

        assert r.status_code == 201

    @pytest.mark.parametrize(
        "field,value",
        [
            ("group_visibility", GroupVisibility.ALL.value),
            ("sector_visibility", SectorVisibility.ALL.value),
        ],
    )
    async def test_a_meeting_for_everyone_is_rejected(
        self, client, db_session, make_user, google_succeeds, field, value
    ):
        professional = _professional(
            make_user, professional_groups=["all"], professional_sectors=["all"]
        )
        _login_as(professional)

        r = await client.post(BASE, json=_payload(**{field: value}))

        assert r.status_code == 422
        assert db_session.query(Meeting).count() == 0

    async def test_a_time_already_past_is_rejected(
        self, client, db_session, make_user, google_succeeds
    ):
        professional = _professional(make_user)
        _login_as(professional)

        r = await client.post(
            BASE,
            json=_payload(
                scheduled_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat()
            ),
        )

        assert r.status_code == 422
        assert google_succeeds == []

    async def test_a_time_without_a_zone_is_refused_not_guessed(
        self, client, db_session, make_user, google_succeeds
    ):
        """
        What an HTML datetime-local input sends: the viewer's local wall-clock
        time, no zone. Read as UTC it would book the meeting three hours late
        in Israel — so it is refused before anything reaches Google.
        """
        professional = _professional(make_user)
        _login_as(professional)
        tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")

        r = await client.post(BASE, json=_payload(scheduled_at=f"{tomorrow}T18:00"))

        assert r.status_code == 422
        assert r.json()["detail"][0]["type"] == "timezone_aware"
        assert google_succeeds == []
        assert db_session.query(Meeting).count() == 0

    async def test_an_israeli_time_is_stored_as_the_same_instant_in_utc(
        self, client, db_session, make_user, google_succeeds
    ):
        """18:00 in Israel (+03:00 in summer) is 15:00 UTC — both in the row
        and in what Google is asked to create."""
        professional = _professional(make_user)
        _login_as(professional)
        tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()

        r = await client.post(
            BASE, json=_payload(scheduled_at=f"{tomorrow.isoformat()}T18:00:00+03:00")
        )

        assert r.status_code == 201
        expected = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 15, 0, 0)
        assert db_session.query(Meeting).one().scheduled_at == expected
        assert google_succeeds[0]["scheduled_at"] == expected

    async def test_the_response_states_its_zone_and_can_be_sent_back(
        self, client, db_session, make_user, google_succeeds
    ):
        """
        The API refuses a naive time, so it must not emit one: a client that
        sends back a scheduled_at it was given would otherwise get a 422 for a
        value this API produced itself.
        """
        professional = _professional(make_user)
        _login_as(professional)

        first = await client.post(BASE, json=_payload())
        assert first.status_code == 201
        body = first.json()
        assert body["scheduled_at"].endswith("Z")
        assert body["created_at"].endswith("Z")

        again = await client.post(
            BASE, json=_payload(scheduled_at=body["scheduled_at"])
        )

        assert again.status_code == 201
        assert again.json()["scheduled_at"] == body["scheduled_at"]

    async def test_a_deactivated_professional_cannot_schedule(
        self, client, db_session, make_user, google_succeeds
    ):
        professional = _professional(make_user)
        professional.is_active_professional = False
        db_session.commit()
        _login_as(professional)

        r = await client.post(BASE, json=_payload())

        assert r.status_code == 403
        assert google_succeeds == []

    async def test_without_a_linked_calendar_the_answer_says_so(
        self, client, db_session, make_user, monkeypatch
    ):
        """
        The real path, not the stub: a professional who never authorised her
        calendar has to get the key the form turns into "connect first", not a
        generic refusal and not a 500 from an unconfigured integration.
        """
        monkeypatch.setattr(
            google_meet_service.settings, "GOOGLE_CLIENT_ID", "client-id"
        )
        monkeypatch.setattr(
            google_meet_service.settings, "GOOGLE_CLIENT_SECRET", "secret"
        )
        professional = _professional(make_user)
        _login_as(professional)

        r = await client.post(BASE, json=_payload())

        assert r.status_code == 403
        assert db_session.query(Meeting).count() == 0


class TestListMeetings:
    async def test_a_member_of_the_cell_sees_it(self, client, db_session, make_user):
        professional = _professional(make_user)
        _make_meeting(db_session, professional)
        _login_as(_member(make_user))

        r = await client.get(BASE)

        assert r.status_code == 200
        assert [m["meet_link"] for m in r.json()] == [MEET_LINK]

    async def test_a_member_of_another_cell_does_not(
        self, client, db_session, make_user
    ):
        professional = _professional(make_user)
        _make_meeting(db_session, professional)
        _login_as(
            _member(
                make_user,
                email="other@example.com",
                user_type=UserType.WIDOW,
                sector=Sector.LITVISH,
            )
        )

        r = await client.get(BASE)

        assert r.status_code == 200
        assert r.json() == []

    async def test_a_finished_meeting_drops_out_but_a_running_one_does_not(
        self, client, db_session, make_user
    ):
        professional = _professional(make_user)
        _make_meeting(db_session, professional, starts_in=-timedelta(hours=5))
        running = _make_meeting(
            db_session, professional, starts_in=-timedelta(minutes=10)
        )
        _login_as(_member(make_user))

        r = await client.get(BASE)

        assert [m["id"] for m in r.json()] == [running.id]

    async def test_a_professional_sees_the_meetings_she_convened(
        self, client, db_session, make_user
    ):
        professional = _professional(make_user)
        meeting = _make_meeting(db_session, professional)
        other = _professional(make_user, email="other-pro@example.com")
        _make_meeting(db_session, other)
        _login_as(professional)

        r = await client.get(BASE)

        assert [m["id"] for m in r.json()] == [meeting.id]

    async def test_a_moderator_sees_the_cells_she_oversees(
        self, client, db_session, make_user
    ):
        professional = _professional(make_user)
        mine = _make_meeting(db_session, professional)
        _make_meeting(
            db_session, professional, sector_visibility=SectorVisibility.LITVISH
        )
        moderator = make_user(
            email="mod@example.com",
            role=UserRole.MODERATOR,
            account_status=AccountStatus.ACTIVE,
        )
        moderator.moderator_cells = [
            {"group": UserType.WIDOW.value, "sector": Sector.HASIDIC.value}
        ]
        db_session.commit()
        _login_as(moderator)

        r = await client.get(BASE)

        assert [m["id"] for m in r.json()] == [mine.id]

    async def test_meetings_come_back_soonest_first(
        self, client, db_session, make_user
    ):
        professional = _professional(make_user)
        later = _make_meeting(db_session, professional, starts_in=timedelta(days=3))
        sooner = _make_meeting(db_session, professional, starts_in=timedelta(hours=2))
        _login_as(_member(make_user))

        r = await client.get(BASE)

        assert [m["id"] for m in r.json()] == [sooner.id, later.id]


class TestModerationOfTheAnnouncementReachesTheList:
    """
    The announcement is what moderation acts on. When it is deleted or hidden,
    the meeting stops being listed — otherwise a moderator removing a
    problematic announcement would leave its join link published anyway.
    """

    async def test_a_moderator_deleting_the_announcement_unlists_the_meeting(
        self, client, db_session, make_user
    ):
        """The scenario end to end, through the real delete endpoint."""
        professional = _professional(make_user)
        meeting = _make_meeting(db_session, professional)
        member = _member(make_user)
        moderator = make_user(
            email="mod@example.com",
            role=UserRole.MODERATOR,
            account_status=AccountStatus.ACTIVE,
        )

        _login_as(member)
        assert [m["id"] for m in (await client.get(BASE)).json()] == [meeting.id]

        _login_as(moderator)
        post = _announcement_of(db_session, meeting)
        r = await client.delete(f"/api/v1/forum/posts/{post.id}")
        assert r.status_code == 200

        _login_as(member)
        r = await client.get(BASE)

        assert r.status_code == 200
        assert r.json() == []
        # Unlisted, not cancelled: the meeting itself is still there.
        assert db_session.query(Meeting).count() == 1

    async def test_an_announcement_hidden_by_reports_unlists_the_meeting(
        self, client, db_session, make_user
    ):
        professional = _professional(make_user)
        _make_meeting(db_session, professional, announcement_status=PostStatus.HIDDEN)
        _login_as(_member(make_user))

        r = await client.get(BASE)

        assert r.json() == []

    async def test_the_meeting_returns_when_the_announcement_is_restored(
        self, client, db_session, make_user
    ):
        """Reversible: reports dismissed, post back to VISIBLE, listed again."""
        professional = _professional(make_user)
        meeting = _make_meeting(
            db_session, professional, announcement_status=PostStatus.HIDDEN
        )
        _login_as(_member(make_user))
        assert (await client.get(BASE)).json() == []

        post = _announcement_of(db_session, meeting)
        post.status = PostStatus.VISIBLE
        db_session.commit()

        r = await client.get(BASE)

        assert [m["id"] for m in r.json()] == [meeting.id]

    @pytest.mark.parametrize("role", [UserRole.PROFESSIONAL, UserRole.ADMIN])
    async def test_the_rule_holds_for_every_role(
        self, client, db_session, make_user, role
    ):
        """Including the professional who convened it and an admin, who
        otherwise see more than a member does."""
        professional = _professional(make_user)
        _make_meeting(db_session, professional, announcement_status=PostStatus.DELETED)
        viewer = (
            professional
            if role == UserRole.PROFESSIONAL
            else make_user(
                email="admin@example.com",
                role=UserRole.ADMIN,
                account_status=AccountStatus.ACTIVE,
            )
        )
        _login_as(viewer)

        r = await client.get(BASE)

        assert r.json() == []


class TestTheAnnouncementIsReadOnly:
    async def _announce(self, client, make_user) -> str:
        professional = _professional(make_user)
        _login_as(professional)
        r = await client.post(BASE, json=_payload())
        assert r.status_code == 201
        return str(r.json()["id"])

    async def test_a_meeting_announcement_cannot_be_liked(
        self, client, db_session, make_user, google_succeeds
    ):
        await self._announce(client, make_user)
        post = db_session.query(ForumPost).one()
        _login_as(_member(make_user))

        r = await client.patch(f"/api/v1/forum/posts/{post.id}/like")

        assert r.status_code == 403

    async def test_an_ordinary_post_can_still_be_liked(
        self, client, db_session, make_user
    ):
        member = _member(make_user)
        post = ForumPost(
            author_id=member.id,
            title="כותרת",
            content="תוכן",
            group_visibility=GroupVisibility.WIDOWS,
            sector_visibility=SectorVisibility.HASIDIC,
            status=PostStatus.VISIBLE,
        )
        db_session.add(post)
        db_session.commit()
        _login_as(member)

        r = await client.patch(f"/api/v1/forum/posts/{post.id}/like")

        assert r.status_code == 200
        assert r.json()["liked"] is True

    async def test_a_meeting_announcement_cannot_be_edited_by_its_author(
        self, client, db_session, make_user, google_succeeds
    ):
        await self._announce(client, make_user)
        post = db_session.query(ForumPost).one()

        r = await client.patch(
            f"/api/v1/forum/posts/{post.id}", json={"title": "כותרת אחרת"}
        )

        assert r.status_code == 403
        db_session.refresh(post)
        assert post.title == "מפגש תמיכה"

    async def test_the_forum_feed_carries_the_meeting_on_the_post(
        self, client, db_session, make_user, google_succeeds
    ):
        await self._announce(client, make_user)
        _login_as(_member(make_user))

        r = await client.get("/api/v1/forum/posts")

        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["post_type"] == PostType.MEETING.value
        assert item["meeting"]["meet_link"] == MEET_LINK
        assert item["meeting"]["duration_minutes"] == 60
        # The join button decides "is it over" from this value, so its zone
        # travels with it rather than being left to the browser to guess.
        assert item["meeting"]["scheduled_at"].endswith("Z")


class TestOrphanedEvents:
    def test_a_failed_write_takes_the_google_event_back_down(
        self, db_session, make_user, monkeypatch
    ):
        """
        The event is created at Google before the rows that record it. If the
        transaction then fails, an event nobody can reach is left in the
        professional's calendar — so create_meeting() removes it rather than
        leaving her to find it.
        """
        from app.schemas.meeting import MeetingCreate

        professional = _professional(make_user)
        deleted: list[str] = []

        monkeypatch.setattr(
            google_meet_service,
            "create_meeting",
            lambda *a, **kw: (MEET_LINK, EVENT_ID),
        )
        monkeypatch.setattr(
            google_meet_service,
            "delete_event",
            lambda db, creator, event_id: deleted.append(event_id),
        )

        def _explode():
            raise RuntimeError("database is gone")

        monkeypatch.setattr(db_session, "commit", _explode)

        with pytest.raises(Exception) as exc_info:
            meeting_service.create_meeting(
                db_session,
                MeetingCreate(
                    title="מפגש תמיכה",
                    scheduled_at=datetime.now(UTC) + timedelta(days=1),
                    group_visibility=GroupVisibility.WIDOWS,
                    sector_visibility=SectorVisibility.HASIDIC,
                ),
                professional,
            )

        assert getattr(exc_info.value, "status_code", None) == 500
        assert deleted == [EVENT_ID]


class TestCalendarConnection:
    """
    The one-time consent step. The status endpoint is what the scheduling form
    asks before it opens, and the callback is where Google returns the browser
    afterwards — with no Authorization header, which is why the signed state
    exists at all.
    """

    @pytest.fixture
    def configured(self, monkeypatch):
        monkeypatch.setattr(
            google_meet_service.settings, "GOOGLE_CLIENT_ID", "client-id"
        )
        monkeypatch.setattr(
            google_meet_service.settings, "GOOGLE_CLIENT_SECRET", "secret"
        )

    async def test_status_reports_not_connected_and_where_to_go(
        self, client, make_user, configured
    ):
        _login_as(_professional(make_user))

        r = await client.get(f"{BASE}/calendar/status")

        assert r.status_code == 200
        body = r.json()
        assert body["connected"] is False
        assert body["connected_at"] is None
        assert body["authorization_url"].startswith(google_meet_service.GOOGLE_AUTH_URL)

    async def test_status_reports_a_linked_calendar_with_a_zoned_timestamp(
        self, client, db_session, make_user, configured
    ):
        from app.core.encryption import encrypt_message
        from app.models.google_calendar_credential import GoogleCalendarCredential

        professional = _professional(make_user)
        encrypted, key_version = encrypt_message("1//refresh")
        db_session.add(
            GoogleCalendarCredential(
                user_id=professional.id,
                refresh_token=encrypted,
                key_version=key_version,
                scope=google_meet_service.settings.GOOGLE_CALENDAR_SCOPE,
            )
        )
        db_session.commit()
        _login_as(professional)

        r = await client.get(f"{BASE}/calendar/status")

        assert r.status_code == 200
        assert r.json()["connected"] is True
        assert r.json()["connected_at"].endswith("Z")

    async def test_status_is_not_a_member_facing_endpoint(
        self, client, make_user, configured
    ):
        _login_as(_member(make_user))

        r = await client.get(f"{BASE}/calendar/status")

        assert r.status_code == 403

    async def test_the_callback_stores_the_grant_and_returns_to_the_app(
        self, client, db_session, make_user, configured, monkeypatch
    ):
        professional = _professional(make_user)
        _login_as(professional)
        state = await self._state_from_status(client)

        monkeypatch.setattr(
            google_meet_service,
            "_post_to_google",
            lambda url, data: {
                "refresh_token": "1//refresh",
                "scope": google_meet_service.settings.GOOGLE_CALENDAR_SCOPE,
            },
        )

        r = await client.get(
            f"{BASE}/calendar/callback", params={"code": "auth-code", "state": state}
        )

        assert r.status_code == 302
        assert r.headers["location"].endswith("?calendar=connected")
        assert google_meet_service.get_credential(db_session, professional.id)

    async def test_declining_consent_is_reported_as_a_choice(
        self, client, db_session, make_user, configured
    ):
        r = await client.get(
            f"{BASE}/calendar/callback", params={"error": "access_denied"}
        )

        assert r.status_code == 302
        assert r.headers["location"].endswith("?calendar=denied")
        assert db_session.query(Meeting).count() == 0

    async def test_a_code_without_a_valid_state_links_nothing(
        self, client, db_session, make_user, configured
    ):
        from app.models.google_calendar_credential import GoogleCalendarCredential

        r = await client.get(
            f"{BASE}/calendar/callback",
            params={"code": "auth-code", "state": "not-a-real-state"},
        )

        assert r.status_code == 302
        assert r.headers["location"].endswith("?calendar=error")
        assert db_session.query(GoogleCalendarCredential).count() == 0

    async def _state_from_status(self, client) -> str:
        from urllib.parse import parse_qs, urlparse

        r = await client.get(f"{BASE}/calendar/status")
        url = r.json()["authorization_url"]
        return str(parse_qs(urlparse(url).query)["state"][0])
