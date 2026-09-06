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
twice, differing only in the header.
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

    def test_wildcard_takes_the_default(self):
        assert negotiate_language("*") is DEFAULT_LANGUAGE

    def test_wildcard_after_a_real_preference_does_not_override_it(self):
        assert negotiate_language("en, *") is Language.EN

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
