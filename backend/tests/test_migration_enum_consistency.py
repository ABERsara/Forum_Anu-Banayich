"""
Regression test for I-03: the auditaction incident (ABF-150) showed a single
sa.Enum(...) call is not the whole story — a type's members can also arrive
later via `ALTER TYPE ... ADD VALUE` in a follow-up migration (the only
correct way to extend an enum that may already be deployed elsewhere; see
[[feedback_never_edit_existing_migrations]]). So this test unions every value
contributed to a given DB enum name across the whole migration history —
whether via sa.Enum(...) or ALTER TYPE ADD VALUE — and compares that combined
set to the Python enum class in app.core.constants exactly.

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
from collections import defaultdict
from pathlib import Path

from app.core import constants

BACKEND_DIR = Path(__file__).parent.parent
MIGRATIONS_DIR = BACKEND_DIR / "migrations" / "versions"

_ADD_VALUE_RE = re.compile(
    r"ALTER TYPE\s+(\w+)\s+ADD VALUE\s+(?:IF NOT EXISTS\s+)?'([^']+)'", re.IGNORECASE
)

# Maps the DB enum type name (sa.Enum(..., name=...)) to its Python source of truth.
ENUM_NAME_TO_CLASS: dict[str, type[enum.Enum]] = {
    cls.__name__.lower(): cls
    for cls in vars(constants).values()
    if isinstance(cls, type) and issubclass(cls, enum.Enum)
}


def _find_enum_calls(path: Path) -> list[tuple[str, list[str]]]:
    """Return (enum_name, member_names) for every Enum(...) call in a migration file.

    Matches both ``sa.Enum`` and ``postgresql.ENUM`` — the latter is used when a
    migration reuses an enum type another migration already created
    (create_type=False), which generic sa.Enum silently ignores.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    results = []
    _enum_names = {"Enum", "ENUM"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_enum_call = (
            isinstance(func, ast.Attribute) and func.attr in _enum_names
        ) or (isinstance(func, ast.Name) and func.id in _enum_names)
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


def _find_add_value_calls(path: Path) -> list[tuple[str, str]]:
    """Return (enum_name, value) for every ALTER TYPE ... ADD VALUE inside an op.execute(...) call.

    Reads the argument via ast rather than grepping the raw file text so that
    a SQL string split across adjacent string literals (to fit the line
    length limit) is still seen whole — the parser joins those into a single
    Constant before this ever runs.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    results = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_execute_call = isinstance(func, ast.Attribute) and func.attr == "execute"
        if not is_execute_call or not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            results.extend(_ADD_VALUE_RE.findall(arg.value))
    return results


def test_all_migration_enums_match_python_source() -> None:
    actual_by_enum: dict[str, set[str]] = defaultdict(set)
    contributing_files: dict[str, set[str]] = defaultdict(set)

    for migration_file in sorted(glob.glob(str(MIGRATIONS_DIR / "*.py"))):
        name = Path(migration_file).name
        for enum_name, member_names in _find_enum_calls(Path(migration_file)):
            actual_by_enum[enum_name].update(member_names)
            contributing_files[enum_name].add(name)
        for enum_name, value in _find_add_value_calls(Path(migration_file)):
            actual_by_enum[enum_name].add(value)
            contributing_files[enum_name].add(name)

    mismatches = []
    for enum_name, actual in actual_by_enum.items():
        enum_cls = ENUM_NAME_TO_CLASS.get(enum_name)
        if enum_cls is None:
            mismatches.append(
                f"{', '.join(contributing_files[enum_name])}: no constants.py enum "
                f"class matches DB enum name '{enum_name}'"
            )
            continue

        expected = {member.name for member in enum_cls}
        if expected != actual:
            mismatches.append(
                f"'{enum_name}' (across {', '.join(contributing_files[enum_name])}) "
                f"values {sorted(actual)} != {enum_cls.__name__} values {sorted(expected)} "
                f"(missing={sorted(expected - actual)}, extra={sorted(actual - expected)})"
            )

    assert not mismatches, "\n".join(mismatches)
