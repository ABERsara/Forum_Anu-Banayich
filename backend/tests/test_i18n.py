"""
Accept-Language support (ABF-137).

Two halves. The first exercises `negotiate_language` and `translate` directly —
header parsing has more edge cases than the endpoints could reasonably cover.
The second drives the real app through the real middleware, because the claim
worth proving is not "translate() returns English" but "a request that says
`Accept-Language: en` gets English back", and everything between those two — the
ContextVar, the threadpool Starlette runs our sync endpoints in, the order the
middleware is installed in — sits in the gap.

TestErrorsInBothLanguages is the ticket's proof of execution: the same request,
twice, differing only in the header. TestWhatDoesNotFollowTheHeader is the other
half of that claim — the constraints Pydantic owns rather than us, which answer
in English either way, and are the one part of a 422 this ticket does not reach.
"""

import asyncio

import pytest

from app.core.i18n import (
    DEFAULT_LANGUAGE,
    Language,
    get_language,
    negotiate_language,
    translate,
)
from app.core.messages import ENGLISH, HEBREW, MESSAGES

BASE = "/api/v1/auth"

VALID_PAYLOAD = {
    "first_name": "שרה",
    "last_name": "לוי",
    "email": "sarah@example.com",
    "phone": "0501234567",
    "birth_date": "1985-03-15",
    "user_type": "widow",
    "sector": "sephardic",
    "id_number": "123456789",
    "password": "StrongPass1!",
}


def _msg(key: str, language: str) -> str:
    return MESSAGES[key][language]


# ---------------------------------------------------------------------------
# header negotiation
# ---------------------------------------------------------------------------


class TestNegotiateLanguage:
    @pytest.mark.parametrize("header", [None, "", "   "])
    def test_no_preference_is_hebrew(self, header):
        assert negotiate_language(header) is Language.HE

    def test_exact_tag(self):
        assert negotiate_language("en") is Language.EN
        assert negotiate_language("he") is Language.HE

    def test_regional_tag_matches_its_primary_subtag(self):
        """A browser sends `en-GB`, not `en`; it still means English."""
        assert negotiate_language("en-GB") is Language.EN
        assert negotiate_language("he-IL") is Language.HE

    def test_tag_is_case_insensitive(self):
        assert negotiate_language("EN-us") is Language.EN

    def test_a_browsers_own_header_is_understood(self):
        """
        The shape a browser attaches to every XHR on its own, unprompted.

        The Angular client overwrites it with the member's chosen UI language
        (`core/interceptors/language.interceptor.ts`) precisely because this
        value reports the locale the *browser* was installed in. A direct API
        caller, though, reaches us with exactly this.
        """
        assert negotiate_language("en-US,en;q=0.9,he;q=0.8") is Language.EN
        assert negotiate_language("he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7") is Language.HE
        assert negotiate_language("ru-RU,ru;q=0.9,en;q=0.8") is Language.EN

    def test_unsupported_language_falls_back(self):
        assert negotiate_language("fr") is DEFAULT_LANGUAGE
        assert negotiate_language("de-AT,fr-FR") is DEFAULT_LANGUAGE

    def test_first_supported_language_wins_over_unsupported_ones(self):
        assert negotiate_language("fr, de, en") is Language.EN

    def test_quality_values_order_the_choice(self):
        """Written worst-first, so only the weights can get this right."""
        assert negotiate_language("en;q=0.2, he;q=0.9") is Language.HE
        assert negotiate_language("he;q=0.2, en;q=0.9") is Language.EN

    def test_equal_quality_keeps_the_order_the_client_wrote(self):
        assert negotiate_language("en;q=0.5, he;q=0.5") is Language.EN

    def test_q_zero_means_not_acceptable(self):
        """`en;q=0` is a refusal of English, not a request for it."""
        assert negotiate_language("en;q=0") is DEFAULT_LANGUAGE
        assert negotiate_language("en;q=0, he") is Language.HE

    def test_refusing_the_default_is_honoured_rather_than_ignored(self):
        """`he;q=0` says *not Hebrew*. Skipping it and then falling back to the
        default hands back the one language the caller ruled out."""
        assert negotiate_language("he;q=0") is Language.EN
        assert negotiate_language("he-IL;q=0") is Language.EN

    def test_refusing_everything_still_gets_an_answer(self):
        """We never answer 406 — out of acceptable options, the default stands
        rather than the request failing over a header."""
        assert negotiate_language("he;q=0, en;q=0") is DEFAULT_LANGUAGE
        assert negotiate_language("*;q=0") is DEFAULT_LANGUAGE

    def test_wildcard_takes_the_default(self):
        assert negotiate_language("*") is DEFAULT_LANGUAGE

    def test_wildcard_after_a_real_preference_does_not_override_it(self):
        assert negotiate_language("en, *") is Language.EN

    def test_wildcard_does_not_reinstate_a_refused_language(self):
        """`he;q=0, *` is "anything but Hebrew" — and `*` sorts ahead of the
        refusal, so the refusal has to be known before the wildcard is read."""
        assert negotiate_language("he;q=0, *") is Language.EN

    def test_malformed_weight_does_not_break_the_request(self):
        """A header we cannot parse costs a preference, never a response."""
        assert negotiate_language("en;q=abc") is Language.EN
        assert negotiate_language(";;;,,,") is DEFAULT_LANGUAGE
        assert negotiate_language("en;;q=;;") is Language.EN


# ---------------------------------------------------------------------------
# the lookup itself
# ---------------------------------------------------------------------------


class TestTranslate:
    def test_outside_a_request_the_language_is_hebrew(self):
        """Unit tests, scripts and jobs call services directly and still get
        the text the platform has always produced."""
        assert get_language() is Language.HE
        assert translate("users.not_found") == _msg("users.not_found", HEBREW)

    def test_unknown_key_comes_back_as_itself(self):
        """The way Transloco renders an unresolved key — never a 500 on an
        error path. test_i18n_catalogue.py is what keeps this unreachable."""
        assert translate("nothing.like.this") == "nothing.like.this"

    def test_placeholders_are_filled(self):
        rendered = translate("agent.rate_limited", limit=25)
        assert "25" in rendered
        assert "{limit}" not in rendered

    def test_a_missing_placeholder_leaves_the_template_rather_than_raising(self):
        assert "{limit}" in translate("agent.rate_limited")


# ---------------------------------------------------------------------------
# the middleware, against the real app
# ---------------------------------------------------------------------------


class TestMiddleware:
    async def test_response_varies_on_accept_language(self, client):
        """Two members get different prose from one URL, so a shared cache has
        to key on the header — otherwise it serves Hebrew to an English reader."""
        r = await client.post(f"{BASE}/register", json=VALID_PAYLOAD)
        assert "accept-language" in r.headers["vary"].lower()

    async def test_language_reaches_a_sync_endpoint(self, client):
        """Every endpoint here is `def`, not `async def`, so Starlette runs it
        in a worker thread. This is the test that the ContextVar survives the
        hop — a message raised by a *service* is what comes back."""
        await client.post(f"{BASE}/register", json=VALID_PAYLOAD)
        r = await client.post(
            f"{BASE}/register", json=VALID_PAYLOAD, headers={"Accept-Language": "en"}
        )
        assert r.status_code == 409
        assert r.json()["detail"] == _msg("auth.email_taken", ENGLISH)

    async def test_pydantic_validator_respects_language(self, client):
        """The request's *other* execution context. A `field_validator` raises
        while the body is still being parsed — before an endpoint exists to run
        at all, and on the event loop rather than in the worker thread the test
        above covers. Same ContextVar, a different moment in the request, and
        the only one of the three shapes whose message reaches the client
        through Pydantic rather than through our own response.

        Asserted whole, not with `in`: `"Value error, "` is Pydantic's prefix
        and part of the 422 contract this ticket promises not to move
        (`TestErrorsInBothLanguages::test_the_422_body_keeps_its_shape`), so
        the equality is what would catch us translating it away by accident.
        The both-languages form of this — the ticket's proof of execution — is
        `TestErrorsInBothLanguages::test_validation_error_follows_the_header`.
        """
        payload = {**VALID_PAYLOAD, "phone": "050-12ab-xyz"}
        r = await client.post(
            f"{BASE}/register", json=payload, headers={"Accept-Language": "en"}
        )
        assert r.status_code == 422
        expected = _msg("validation.phone_digits_only", ENGLISH)
        assert r.json()["detail"][0]["msg"] == f"Value error, {expected}"

    async def test_concurrent_requests_do_not_share_a_language(self, client):
        """The reason this is a ContextVar and not a module-level global: two
        requests in flight at once must not read each other's header."""
        await client.post(f"{BASE}/register", json=VALID_PAYLOAD)

        async def register(language):
            return await client.post(
                f"{BASE}/register",
                json=VALID_PAYLOAD,
                headers={"Accept-Language": language},
            )

        english, hebrew = await asyncio.gather(
            *[register("en"), register("he")],
        )
        assert english.json()["detail"] == _msg("auth.email_taken", ENGLISH)
        assert hebrew.json()["detail"] == _msg("auth.email_taken", HEBREW)


# ---------------------------------------------------------------------------
# proof of execution — the same request, twice, one header apart
# ---------------------------------------------------------------------------


class TestErrorsInBothLanguages:
    """
    One case per pattern the ticket mapped, each asserted in both languages:
    a Pydantic validator (422), an HTTPException raised in a service (409),
    an HTTPException raised by a dependency (401), and a success dict (200).

    Organised by the *requirement*, where TestMiddleware above is organised by
    the *mechanism* — so the validator case is proved in both places on purpose:
    here as the ticket's worked example, there as one of the three moments in a
    request at which the ContextVar is read.
    """

    async def test_validation_error_follows_the_header(self, client):
        """The ticket's worked example: an invalid phone number."""
        payload = {**VALID_PAYLOAD, "phone": "050-12ab-xyz"}

        english = await client.post(
            f"{BASE}/register", json=payload, headers={"Accept-Language": "en"}
        )
        hebrew = await client.post(
            f"{BASE}/register", json=payload, headers={"Accept-Language": "he"}
        )

        assert english.status_code == hebrew.status_code == 422
        assert (
            _msg("validation.phone_digits_only", ENGLISH)
            in english.json()["detail"][0]["msg"]
        )
        assert (
            _msg("validation.phone_digits_only", HEBREW)
            in hebrew.json()["detail"][0]["msg"]
        )

    async def test_the_422_body_keeps_its_shape(self, client):
        """Only the half of `msg` we wrote changes. Pydantic's `Value error, `
        prefix, the `loc`, and the error `type` are contract, and a client
        reading them must not have to care which language it asked for."""
        payload = {**VALID_PAYLOAD, "phone": "050-12ab-xyz"}
        r = await client.post(
            f"{BASE}/register", json=payload, headers={"Accept-Language": "en"}
        )
        error = r.json()["detail"][0]
        assert error["type"] == "value_error"
        assert error["loc"] == ["body", "phone"]
        assert error["msg"].startswith("Value error, ")

    async def test_service_error_follows_the_header(self, client):
        await client.post(f"{BASE}/register", json=VALID_PAYLOAD)

        english = await client.post(
            f"{BASE}/register", json=VALID_PAYLOAD, headers={"Accept-Language": "en"}
        )
        hebrew = await client.post(
            f"{BASE}/register", json=VALID_PAYLOAD, headers={"Accept-Language": "he"}
        )

        assert english.json()["detail"] == _msg("auth.email_taken", ENGLISH)
        assert hebrew.json()["detail"] == _msg("auth.email_taken", HEBREW)

    async def test_dependency_error_follows_the_header(self, client):
        """`get_current_user` builds its 401 before any endpoint code runs."""
        english = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer nonsense", "Accept-Language": "en"},
        )
        hebrew = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer nonsense", "Accept-Language": "he"},
        )

        assert english.status_code == hebrew.status_code == 401
        assert english.json()["detail"] == _msg("errors.unauthenticated", ENGLISH)
        assert hebrew.json()["detail"] == _msg("errors.unauthenticated", HEBREW)

    async def test_success_message_follows_the_header(self, client):
        """Not every translated string is an error — the ticket's third
        pattern is a plain dict returned from a 200."""
        english = await client.post(
            f"{BASE}/register", json=VALID_PAYLOAD, headers={"Accept-Language": "en"}
        )
        assert english.json()["message"] == _msg("auth.registered", ENGLISH)

    async def test_english_response_carries_no_hebrew(self, client):
        """The `not.toMatch(HEBREW)` sweep the frontend i18n tickets used, on
        this side of the wire: an English reader should see no Hebrew at all."""
        await client.post(f"{BASE}/register", json=VALID_PAYLOAD)
        r = await client.post(
            f"{BASE}/register", json=VALID_PAYLOAD, headers={"Accept-Language": "en"}
        )
        assert not any("֐" <= ch <= "׿" for ch in r.text)


# ---------------------------------------------------------------------------
# where the ticket stops
# ---------------------------------------------------------------------------


class TestWhatDoesNotFollowTheHeader:
    """
    The boundary of ABF-137, pinned rather than left to be rediscovered.

    This ticket translates the messages *we* write. A field that fails one of
    Pydantic's own constraints — `min_length`, `EmailStr`, an enum member, an
    absent key — never reaches a validator of ours, so its `msg` is Pydantic's
    English for every caller, a Hebrew reader included. `main` already answered
    that way; this ticket neither causes it nor closes it.

    Closing it is a ticket of its own, and a bigger one than it looks. It means
    a `RequestValidationError` handler keyed on the machine-readable `type`
    (`string_too_short`, `enum`, `missing`) — not on `msg`, which is the
    prose-parsing that i18n.py's docstring rejects — plus a catalogue entry per
    type and a `ctx` mapping for the numbers inside them. It would also rewrite
    `detail[].msg` for every endpoint in the API, and *this* ticket's contract
    is that the 422 body does not move.

    So the gap is written down as a test instead of a comment: this fails the
    day someone does translate them, and asks them to delete it on the way.
    """

    @pytest.mark.parametrize(
        ("payload", "error_type"),
        [
            ({**VALID_PAYLOAD, "phone": "abc"}, "string_too_short"),
            ({**VALID_PAYLOAD, "email": "not-an-email"}, "value_error"),
            ({**VALID_PAYLOAD, "user_type": "wizard"}, "enum"),
            ({k: v for k, v in VALID_PAYLOAD.items() if k != "phone"}, "missing"),
        ],
        ids=["too short", "not an email", "outside the enum", "absent"],
    )
    async def test_a_constraint_pydantic_owns_answers_the_same_either_way(
        self, client, payload, error_type
    ):
        english = await client.post(
            f"{BASE}/register", json=payload, headers={"Accept-Language": "en"}
        )
        hebrew = await client.post(
            f"{BASE}/register", json=payload, headers={"Accept-Language": "he"}
        )

        assert english.status_code == hebrew.status_code == 422
        english_error = english.json()["detail"][0]
        assert english_error["type"] == error_type
        # The claim, in two halves: the header changes nothing here, and the
        # text is not one of ours to have changed.
        assert english_error["msg"] == hebrew.json()["detail"][0]["msg"]
        assert english_error["msg"] not in {
            text for translations in MESSAGES.values() for text in translations.values()
        }

    async def test_a_constraint_we_own_still_follows_the_header(self, client):
        """The other side of the same 422, so the boundary reads as a boundary
        and not as "validation errors are untranslated". `min_length` on
        `phone` is Pydantic's; `phone_digits_only` on the same field is ours,
        and only the second one changes language."""
        payload = {**VALID_PAYLOAD, "phone": "050-12ab-xyz"}
        english = await client.post(
            f"{BASE}/register", json=payload, headers={"Accept-Language": "en"}
        )
        hebrew = await client.post(
            f"{BASE}/register", json=payload, headers={"Accept-Language": "he"}
        )

        assert english.json()["detail"][0]["type"] == "value_error"
        assert english.json()["detail"][0]["msg"] != hebrew.json()["detail"][0]["msg"]


class TestHebrewIsUnchanged:
    """
    The acceptance criterion that is easy to break and easy to overlook: a
    client that sends no header at all — every client shipping today, the
    Angular app included — must not notice this ticket happened.
    """

    async def test_no_header_still_answers_in_hebrew(self, client):
        await client.post(f"{BASE}/register", json=VALID_PAYLOAD)
        r = await client.post(f"{BASE}/register", json=VALID_PAYLOAD)
        assert r.json()["detail"] == _msg("auth.email_taken", HEBREW)

    async def test_an_unsupported_language_answers_in_hebrew(self, client):
        await client.post(f"{BASE}/register", json=VALID_PAYLOAD)
        r = await client.post(
            f"{BASE}/register", json=VALID_PAYLOAD, headers={"Accept-Language": "fr-CA"}
        )
        assert r.json()["detail"] == _msg("auth.email_taken", HEBREW)
