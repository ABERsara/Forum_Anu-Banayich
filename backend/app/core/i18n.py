"""
Request-scoped language negotiation, and the lookup that uses it.

The problem this solves
-----------------------
Services raise `HTTPException` deep below the endpoint, and Pydantic validators
run before the endpoint body exists at all. Neither has a `Request` to read
`Accept-Language` from, and threading one down through every service signature
would put an HTTP concern into functions whose whole job is domain logic.

So the negotiated language lives in a `ContextVar` that `LanguageMiddleware`
sets once per request, and `translate()` reads at the moment a message is built.
A ContextVar is the right shape here because it is per-task, not per-process:
two requests being served concurrently never see each other's language.

One mechanism, not two
----------------------
The three shapes a user-facing message arrives in — `HTTPException(detail=...)`,
a `ValueError` from a Pydantic `field_validator`, and a success `dict` returned
straight from an endpoint — look like they need separate handling, and ABF-137
was written expecting they would. They do not. All three are *built* while the
request is being served, so all three can simply call `translate()` where they
already build their string, and the ContextVar is set for each of them.

That matters most for the validator case. The alternative was a custom
`RequestValidationError` handler that re-reads `detail[].msg`, strips the
`"Value error, "` prefix Pydantic puts there, and swaps the remainder — parsing
a human-readable string out of another library's error format to get a key back.
`translate()` at the `raise` keeps the key from ever becoming prose in the first
place, and leaves the 422 body byte-identical to what it was before.

Why a raw ASGI middleware and not `@app.middleware("http")`
-----------------------------------------------------------
Starlette's `BaseHTTPMiddleware` — what the decorator builds — runs the rest of
the app in a *separate* anyio task. Context set before `call_next` does reach it
today, but the value is a copy, and the reverse direction never propagates. A
plain ASGI callable runs the downstream app in the caller's own context, so
there is no copy and no ordering subtlety to reason about. Endpoints here are
sync `def`, which Starlette runs in a worker thread; anyio copies the context
into that thread, so the value survives (pinned by
`test_i18n.py::test_language_reaches_a_sync_endpoint`).

Defaulting
----------
`DEFAULT_LANGUAGE` is Hebrew, and the ContextVar carries that default outside a
request too — so a service called directly from a unit test, a script, or a
background job still produces the Hebrew text it always did.
"""

import enum
from contextvars import ContextVar
from typing import Final

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.messages import MESSAGES


class Language(enum.StrEnum):
    """A language the API can answer in — mirrors the client's `AppLang`."""

    HE = "he"
    EN = "en"


#: What the API answers in when the request does not ask for anything it has,
#: and what every call outside a request context gets.
DEFAULT_LANGUAGE: Final = Language.HE

#: The language of the request currently being served.
_current_language: ContextVar[Language] = ContextVar(
    "current_language", default=DEFAULT_LANGUAGE
)


def _parse_accept_language(header: str) -> list[tuple[str, float]]:
    """
    Split an Accept-Language header into (tag, quality) pairs, best first.

    Follows RFC 9110 §12.5.4: comma-separated tags, each optionally carrying a
    `;q=` weight that defaults to 1. A malformed weight is treated as absent
    rather than failing the request — a header we cannot parse should cost the
    caller their preferred language, never their response.
    """
    parsed: list[tuple[int, str, float]] = []
    for index, part in enumerate(header.split(",")):
        tag, _, params = part.strip().partition(";")
        tag = tag.strip().lower()
        if not tag:
            continue
        quality = 1.0
        for param in params.split(";"):
            name, _, value = param.partition("=")
            if name.strip().lower() == "q":
                try:
                    quality = float(value.strip())
                except ValueError:
                    quality = 1.0
        # `index` keeps the sort stable: equal weights hold the order the
        # client wrote them in, which is the order it prefers them in.
        parsed.append((index, tag, quality))

    parsed.sort(key=lambda item: (-item[2], item[0]))
    return [(tag, quality) for _, tag, quality in parsed]


def _fallback_language(refused: set[str]) -> Language:
    """
    What to answer when the header named nothing we have.

    Normally that is the default. The exception is a header that refused the
    default outright (`he;q=0`): handing back Hebrew is then the one answer the
    caller explicitly told us not to give, so any other language we have and
    they did not refuse is a better one. If they refused everything, we are out
    of honest options and the default stands — this API never answers 406.
    """
    if DEFAULT_LANGUAGE.value not in refused:
        return DEFAULT_LANGUAGE
    for language in Language:
        if language is not DEFAULT_LANGUAGE and language.value not in refused:
            return language
    return DEFAULT_LANGUAGE


def negotiate_language(header: str | None) -> Language:
    """
    Pick the best language this API supports out of an Accept-Language header.

    Matches a full tag (`en`) and the primary subtag of a regional one
    (`en-GB` → `en`), so a browser sending its own locale still gets English.
    `q=0` means "not acceptable", and `*` means "anything you have" — both hand
    off to `_fallback_language`, which is what keeps a refusal honoured rather
    than merely skipped. Anything unrecognised falls through to the default
    rather than erroring.
    """
    if not header:
        return DEFAULT_LANGUAGE

    supported = {language.value: language for language in Language}
    parsed = _parse_accept_language(header)
    # Collected up front, not as we go: `*` can sort ahead of the tag that was
    # refused (`he;q=0, *`), and by then the refusal has to be known already.
    refused = {tag.partition("-")[0] for tag, quality in parsed if quality <= 0}

    for tag, quality in parsed:
        if quality <= 0:
            continue
        if tag == "*":
            return _fallback_language(refused)
        primary = tag.partition("-")[0]
        if primary in supported:
            return supported[primary]

    return _fallback_language(refused)


def get_language() -> Language:
    """The language of the request being served, or the default outside one."""
    return _current_language.get()


def translate(key: str, /, **params: object) -> str:
    """
    Render a catalogue message in the current request's language.

    `key` is positional-only so a message that itself needs a `key` parameter
    cannot collide with it.

    Two deliberate softenings, both because this runs on the error path and an
    i18n slip must never turn a clean 4xx into a 500:
      - an unknown key comes back as the key itself, the way Transloco renders
        an unresolved key on the client;
      - a placeholder with no matching argument leaves the template unformatted.
    `tests/test_i18n_catalogue.py` is what keeps either from ever happening —
    it walks the source for every `translate()` call and checks it against the
    catalogue, so these paths stay unreachable rather than merely survivable.
    """
    translations = MESSAGES.get(key)
    if translations is None:
        return key

    language = get_language()
    text = translations.get(language, translations[DEFAULT_LANGUAGE])
    if not params:
        return text
    try:
        return text.format(**params)
    except (KeyError, IndexError):
        return text


class LanguageMiddleware:
    """
    Reads Accept-Language once per request and publishes it to the ContextVar.

    Also sets `Vary: Accept-Language` on the way out. Two members asking for the
    same URL now get different prose, so any cache between us and them has to
    key on the header — without `Vary`, a shared cache is free to hand a Hebrew
    error to someone reading the site in English.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        header = Headers(scope=scope).get("accept-language")
        token = _current_language.set(negotiate_language(header))

        async def send_with_vary(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("vary", "Accept-Language")
            await send(message)

        try:
            await self.app(scope, receive, send_with_vary)
        finally:
            _current_language.reset(token)
