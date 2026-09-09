"""
Guards on the message catalogue itself, and on the source that uses it.

These read `app/` as text rather than importing and calling it. That is the
point: the thing ABF-137 has to keep true is a property of the *whole* backend
— "no user-facing message is written in one language at the point it is raised"
— and no runtime test can cover a `raise` that no test happens to reach.

`test_no_message_is_raised_in_hebrew` is the one that matters most. It is what
makes the next person's new endpoint fail here instead of shipping a Hebrew-only
error, and it is the reason the count in the PR description is a fact rather
than a claim.
"""

import ast
import re
from pathlib import Path

import pytest

from app.core.messages import ENGLISH, HEBREW, MESSAGES

APP = Path(__file__).resolve().parent.parent / "app"

HEBREW_CHARACTER = re.compile("[֐-׿]")
PLACEHOLDER = re.compile(r"\{(\w+)\}")

# There is deliberately no per-file exemption list here.
#
# The modules whose Hebrew ABF-137 leaves alone — email templates, the
# organisation's name, the label maps (the reasoning for each is in
# app/core/messages.py's docstring) — do not need one, because this check is
# scoped by *shape* rather than by file: it only ever looks inside
# `HTTPException(detail=…)`, `ValueError(…)` and a `{"message"/"detail": …}`
# dict. None of that deferred Hebrew is in any of those, so exempting the files
# bought nothing and cost the one thing the check is for — a Hebrew
# `HTTPException` added to email_service.py tomorrow would have passed in
# silence.
# `test_a_formerly_exempt_module_is_not_a_blind_spot` pins that it no longer
# does. Being scoped by shape is also what lets a module arrive without anyone
# remembering to list it here: when ABF-122 lands again, agent_service.py and
# llm_service.py are held to this rule on the day they reappear.


def _sources():
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, path.relative_to(APP).as_posix(), path.read_text(encoding="utf-8")


def _module_string_constants(tree):
    """Module-level `NAME = "..."` — how forum_service holds a key that is
    raised from several places."""
    return {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        for target in node.targets
        if isinstance(target, ast.Name) and isinstance(node.value.value, str)
    }


def _is_translate_call(node):
    """
    `translate(...)` or `i18n.translate(...)` — the two ways this module gets
    imported.

    Deliberately not *any* `.translate(`: `str.translate` is a builtin, and
    mistaking one for a catalogue lookup would fail the suite on code that has
    nothing to do with i18n.
    """
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "translate"
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "translate"
        and isinstance(func.value, ast.Name)
        and func.value.id == "i18n"
    )


def _translate_keys():
    """Every key passed to translate(), resolving the constants indirection."""
    keys = []
    for _, rel, source in _sources():
        tree = ast.parse(source)
        constants = _module_string_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_translate_call(node) or not node.args:
                continue
            argument = node.args[0]
            if isinstance(argument, ast.Constant):
                keys.append((rel, node.lineno, argument.value))
            elif isinstance(argument, ast.Name) and argument.id in constants:
                keys.append((rel, node.lineno, constants[argument.id]))
            else:
                pytest.fail(
                    f"{rel}:{node.lineno} calls translate() with an argument this "
                    f"check cannot resolve, so the key cannot be verified: "
                    f"{ast.unparse(argument)}"
                )
    return keys


# ---------------------------------------------------------------------------
# the catalogue
# ---------------------------------------------------------------------------


class TestCatalogue:
    def test_every_message_exists_in_both_languages(self):
        """The frontend's he.json/en.json parity check, on the server side."""
        missing = {
            key: sorted({HEBREW, ENGLISH} - set(translations))
            for key, translations in MESSAGES.items()
            if {HEBREW, ENGLISH} - set(translations)
        }
        assert missing == {}

    def test_no_message_is_blank(self):
        blank = [
            f"{key}.{language}"
            for key, translations in MESSAGES.items()
            for language, text in translations.items()
            if not text.strip()
        ]
        assert blank == []

    def test_no_language_carries_a_stray_extra_entry(self):
        extra = {
            key: sorted(set(translations) - {HEBREW, ENGLISH})
            for key, translations in MESSAGES.items()
            if set(translations) - {HEBREW, ENGLISH}
        }
        assert extra == {}

    def test_the_english_side_has_no_hebrew_left_in_it(self):
        """Catches the copy-paste that leaves a half-translated entry behind."""
        untranslated = [
            key
            for key, translations in MESSAGES.items()
            if HEBREW_CHARACTER.search(translations[ENGLISH])
        ]
        assert untranslated == []

    def test_placeholders_match_across_languages(self):
        """
        A translator dropping a `{placeholder}` would silently ship a message
        with the number missing — `translate()` fills what the template asks
        for, and fills it per language.

        No entry carries a placeholder today: `agent.rate_limited` was the only
        one and it left with `main`'s revert of ABF-122. The check stays because
        the cost of keeping it is nothing and the failure it catches is silent;
        `test_i18n.py::TestTranslate` covers the rendering itself against an
        entry it supplies.
        """
        mismatched = {
            key: (
                sorted(PLACEHOLDER.findall(translations[HEBREW])),
                sorted(PLACEHOLDER.findall(translations[ENGLISH])),
            )
            for key, translations in MESSAGES.items()
            if sorted(PLACEHOLDER.findall(translations[HEBREW]))
            != sorted(PLACEHOLDER.findall(translations[ENGLISH]))
        }
        assert mismatched == {}

    def test_no_two_keys_hold_the_same_hebrew(self):
        """Two keys for one message is how the platform ends up saying the same
        thing two different ways once someone edits only one of them."""
        seen: dict[str, str] = {}
        duplicates = []
        for key, translations in MESSAGES.items():
            text = translations[HEBREW]
            if text in seen:
                duplicates.append((seen[text], key))
            seen[text] = key
        assert duplicates == []

    def test_keys_are_namespaced(self):
        assert [key for key in MESSAGES if "." not in key] == []


# ---------------------------------------------------------------------------
# the catalogue against the code
# ---------------------------------------------------------------------------


class TestCatalogueMatchesTheCode:
    def test_every_key_used_in_the_app_is_defined(self):
        """An unresolved key renders as itself — a member would read
        `users.not_found` on the screen. This is why that never happens."""
        undefined = [
            f"{rel}:{line} -> {key}"
            for rel, line, key in _translate_keys()
            if key not in MESSAGES
        ]
        assert undefined == []

    def test_every_key_in_the_catalogue_is_used(self):
        """Dead entries are how a catalogue rots: they get translated, reviewed
        and maintained long after the message they belonged to was deleted."""
        used = {key for _, _, key in _translate_keys()}
        assert sorted(set(MESSAGES) - used) == []


# ---------------------------------------------------------------------------
# the property the ticket is actually about
# ---------------------------------------------------------------------------


class TestNoHardcodedMessages:
    """
    Walks every module for a user-facing message written as a literal.

    The three shapes ABF-137 mapped: `HTTPException(detail=...)`, a `ValueError`
    from a Pydantic validator, and a `{"message": ...}` dict returned from an
    endpoint. A Hebrew literal in any of them is a message that cannot follow
    Accept-Language, wherever in the backend it was added.
    """

    def _offenders(self, sources=None):
        """
        `sources` is `(module path, source)` pairs, defaulting to real `app/`.

        Passing them in is what lets the guard be run against a *known*
        violation — including one placed in a module the check used to exempt.
        """
        if sources is None:
            sources = [(rel, source) for _, rel, source in _sources()]
        found = []
        for rel, source in sources:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                for label, value in self._message_expressions(node):
                    if any(
                        isinstance(child, ast.Constant)
                        and isinstance(child.value, str)
                        and HEBREW_CHARACTER.search(child.value)
                        for child in ast.walk(value)
                    ):
                        found.append(f"{rel}:{value.lineno} ({label})")
        return found

    @staticmethod
    def _message_expressions(node):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", getattr(node.func, "attr", None))
            if name == "HTTPException":
                for keyword in node.keywords:
                    if keyword.arg == "detail":
                        yield "HTTPException(detail=...)", keyword.value
            elif name == "ValueError":
                for argument in node.args[:1]:
                    yield "ValueError(...)", argument
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in ("message", "detail"):
                    yield f'{{"{key.value}": ...}}', value

    def test_no_message_is_raised_in_hebrew(self):
        assert self._offenders() == []

    @pytest.mark.parametrize(
        ("shape", "source"),
        [
            (
                "HTTPException(detail=...)",
                'raise HTTPException(status_code=404, detail="לא נמצא")',
            ),
            (
                "ValueError(...)",
                'raise ValueError("מספר הטלפון חייב להכיל ספרות בלבד")',
            ),
            ('{"message": ...}', '{"message": "נרשמת בהצלחה."}'),
        ],
    )
    def test_the_check_can_actually_see_a_violation(self, shape, source):
        """A guard nobody has watched fail is a guard nobody should trust — so
        watch it fail, once for each of the three shapes ABF-137 mapped."""
        assert self._offenders([("services/some_service.py", source)]) == [
            f"services/some_service.py:1 ({shape})"
        ]

    def test_a_formerly_exempt_module_is_not_a_blind_spot(self):
        """
        ABF-137 first shipped this check with a per-file exemption list, which
        included email_service.py for the Hebrew in its templates. A Hebrew
        HTTPException added there would have passed in silence. Scoping by shape
        instead of by file is what closed that, and this is the test that says
        so.

        The source is passed in rather than read off disk on purpose: what is
        being asserted is that the *module's name* buys it nothing, which is
        exactly what a real file could not demonstrate — it has no violation in
        it, and the check would pass either way.
        """
        violation = 'raise HTTPException(status_code=503, detail="השירות אינו זמין")'
        assert self._offenders([("services/email_service.py", violation)]) == [
            "services/email_service.py:1 (HTTPException(detail=...))"
        ]
