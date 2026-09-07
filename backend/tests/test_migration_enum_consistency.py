"""
Regression test for I-03: the enum members the alembic migrations create must
match the Python enum classes in app.core.constants exactly.

A DB enum type's members come from two places in the migrations:
  * the sa.Enum(...) / postgresql.ENUM(...) call that first creates it, and
  * any later `ALTER TYPE <name> ADD VALUE '<MEMBER>'` migration that extends it.

The two are matched only by enum type name — this test does not verify that
the ALTER TYPE migration is actually a descendant of the creating one (that
ordering is covered by test_migration.py running `alembic upgrade head`).

SQLite doesn't enforce enum membership (see test_migration.py — the column is
just VARCHAR with no CHECK constraint), so a real Postgres instance is the
only way to observe the resulting constraint-violation crash at runtime. This
test catches the drift statically instead, without needing Postgres.
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

# `ALTER TYPE [schema.]auditaction ADD VALUE [IF NOT EXISTS] 'AGENT_CONVERSATION'`
# — tolerant of whitespace/newlines, an optional schema qualifier, and quoted
# identifiers. The label group is compared against the Python enum's member
# NAMES, so a value like 'agent_conversation' is still captured and then flagged
# as an `extra=` mismatch rather than silently ignored.
_ALTER_ADD_VALUE = re.compile(
    r"ALTER\s+TYPE\s+(?:\"?\w+\"?\.)?\"?(\w+)\"?\s+ADD\s+VALUE\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?'(\w+)'",
    re.IGNORECASE,
)


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


def _find_alter_type_additions(path: Path) -> list[tuple[str, str]]:
    """Return (enum_name, member_name) for every `ALTER TYPE ... ADD VALUE`
    actually executed by a migration's upgrade().

    Only string literals passed to an ``.execute(...)`` call inside the
    ``upgrade`` function body count — a commented-out or relocated statement, or
    SQL that is built into a variable but never executed, does not, matching the
    AST rigor of _find_enum_calls().
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    upgrade = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
        ),
        None,
    )
    if upgrade is None:
        return []
    results: list[tuple[str, str]] = []
    for node in ast.walk(upgrade):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
        ):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                results.extend(_ALTER_ADD_VALUE.findall(arg.value))
    return results


def test_all_migration_enums_match_python_source() -> None:
    migration_files = [Path(p) for p in sorted(glob.glob(str(MIGRATIONS_DIR / "*.py")))]

    # Members added to a DB enum type by a later ALTER TYPE ... ADD VALUE, keyed
    # by the enum type name — folded into every sa.Enum() check for that type.
    alter_added: dict[str, set[str]] = {}
    for migration_file in migration_files:
        for enum_name, member in _find_alter_type_additions(migration_file):
            alter_added.setdefault(enum_name, set()).add(member)

    mismatches = []
    for migration_file in migration_files:
        for enum_name, migration_values in _find_enum_calls(migration_file):
            enum_cls = ENUM_NAME_TO_CLASS.get(enum_name)
            if enum_cls is None:
                mismatches.append(
                    f"{migration_file.name}: no constants.py enum class matches "
                    f"DB enum name '{enum_name}'"
                )
                continue

            expected = {member.name for member in enum_cls}
            actual = set(migration_values) | alter_added.get(enum_name, set())
            if expected != actual:
                mismatches.append(
                    f"{migration_file.name}: '{enum_name}' migration values "
                    f"{sorted(actual)} != {enum_cls.__name__} values {sorted(expected)} "
                    f"(missing={sorted(expected - actual)}, extra={sorted(actual - expected)})"
                )

    assert not mismatches, "\n".join(mismatches)
