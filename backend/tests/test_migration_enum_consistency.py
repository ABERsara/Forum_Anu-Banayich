"""
Regression test for I-03: DB enum types in the alembic migrations must match
the Python enum classes in app.core.constants exactly.

SQLite doesn't enforce enum membership (see test_migration.py — the column is
just VARCHAR with no CHECK constraint), so a real Postgres instance is the
only way to observe the resulting constraint-violation crash at runtime. This
test catches the drift statically instead, without needing Postgres.

A shipped migration is never edited in place, not even to add one enum value
to its own sa.Enum(...) list (see feedback_never_edit_existing_migrations in
project memory — ABF-118 did that once, and it silently left 6 values missing
on the deployed database, since Alembic never re-runs a revision that already
executed there). So a type's *current* member list is never expected to sit
in any single migration file: it is whatever the sa.Enum(...) that created it
declared, plus every `ALTER TYPE ... ADD VALUE` a later migration added on
top (see e.g. b3e9f2a6c1d4_add_closed_account_deleted_to_.py) — the union of
those, across every migration that has ever touched the type.
"""

import ast
import enum
import glob
import re
from pathlib import Path

from app.core import constants

BACKEND_DIR = Path(__file__).parent.parent
MIGRATIONS_DIR = BACKEND_DIR / "migrations" / "versions"

# Maps the DB enum type name (sa.Enum(..., name=...)) to its Python source of truth.
ENUM_NAME_TO_CLASS: dict[str, type[enum.Enum]] = {
    cls.__name__.lower(): cls
    for cls in vars(constants).values()
    if isinstance(cls, type) and issubclass(cls, enum.Enum)
}

# `ALTER TYPE <name> ADD VALUE [IF NOT EXISTS] '<value>'` — how a migration
# grows an existing enum type without redeclaring it. Matched as plain text
# rather than parsed as SQL: op.execute() takes a literal string in every
# migration in this repo, and a regex is enough to read one back out.
_ALTER_TYPE_ADD_VALUE = re.compile(
    r"ALTER TYPE (\w+) ADD VALUE(?: IF NOT EXISTS)? '(\w+)'"
)


def _find_enum_calls(path: Path) -> list[tuple[str, list[str]]]:
    """Return (enum_name, member_names) for every sa.Enum(...) call in a migration file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    results = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_enum_call = (isinstance(func, ast.Attribute) and func.attr == "Enum") or (
            isinstance(func, ast.Name) and func.id == "Enum"
        )
        if not is_enum_call:
            continue
        member_names = [
            arg.value
            for arg in node.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        ]
        enum_name = next(
            (
                kw.value.value
                for kw in node.keywords
                if kw.arg == "name"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ),
            None,
        )
        if enum_name:
            results.append((enum_name, member_names))
    return results


def _find_alter_type_add_values(path: Path) -> list[tuple[str, str]]:
    """Return (enum_name, value) for every ALTER TYPE ... ADD VALUE statement."""
    return _ALTER_TYPE_ADD_VALUE.findall(path.read_text(encoding="utf-8"))


def test_all_migration_enums_match_python_source() -> None:
    values_by_enum: dict[str, set[str]] = {}

    for migration_file in sorted(glob.glob(str(MIGRATIONS_DIR / "*.py"))):
        path = Path(migration_file)
        for enum_name, member_names in _find_enum_calls(path):
            values_by_enum.setdefault(enum_name, set()).update(member_names)
        for enum_name, value in _find_alter_type_add_values(path):
            values_by_enum.setdefault(enum_name, set()).add(value)

    mismatches = []
    for enum_name, actual in values_by_enum.items():
        enum_cls = ENUM_NAME_TO_CLASS.get(enum_name)
        if enum_cls is None:
            mismatches.append(
                f"no constants.py enum class matches DB enum name '{enum_name}'"
            )
            continue

        expected = {member.name for member in enum_cls}
        if expected != actual:
            mismatches.append(
                f"'{enum_name}' migration values (aggregated across all migrations) "
                f"{sorted(actual)} != {enum_cls.__name__} values {sorted(expected)} "
                f"(missing={sorted(expected - actual)}, extra={sorted(actual - expected)})"
            )

    assert not mismatches, "\n".join(mismatches)
