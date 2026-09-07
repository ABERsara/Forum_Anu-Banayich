"""
Regression test for I-03: sa.Enum(...) values in the alembic migrations must
match the Python enum classes in app.core.constants exactly.

SQLite doesn't enforce enum membership (see test_migration.py — the column is
just VARCHAR with no CHECK constraint), so a real Postgres instance is the
only way to observe the resulting constraint-violation crash at runtime. This
test catches the drift statically instead, without needing Postgres.
"""

import ast
import enum
import glob
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


def test_all_migration_enums_match_python_source() -> None:
    mismatches = []

    for migration_file in sorted(glob.glob(str(MIGRATIONS_DIR / "*.py"))):
        for enum_name, migration_values in _find_enum_calls(Path(migration_file)):
            enum_cls = ENUM_NAME_TO_CLASS.get(enum_name)
            if enum_cls is None:
                mismatches.append(
                    f"{Path(migration_file).name}: no constants.py enum class matches "
                    f"DB enum name '{enum_name}'"
                )
                continue

            expected = {member.name for member in enum_cls}
            actual = set(migration_values)
            if expected != actual:
                mismatches.append(
                    f"{Path(migration_file).name}: '{enum_name}' migration values "
                    f"{sorted(actual)} != {enum_cls.__name__} values {sorted(expected)} "
                    f"(missing={sorted(expected - actual)}, extra={sorted(actual - expected)})"
                )

    assert not mismatches, "\n".join(mismatches)
