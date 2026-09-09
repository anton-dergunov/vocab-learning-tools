"""The layering, enforced by imports rather than by remembering it.

Two rules, each of which stops being true silently. `api/` may not import `jobs/`, because capture,
review and the sync API must work with the orchestrator down and must not know one exists. And
nothing outside `repository/` may touch the database, which is the server-side twin of the rule the
interface already lives by.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[3] / "src" / "acervo"


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def modules_under(*parts: str) -> list[Path]:
    return sorted((PACKAGE.joinpath(*parts)).rglob("*.py"))


@pytest.mark.parametrize("path", modules_under("api"), ids=lambda path: path.name)
def test_the_request_path_does_not_import_batch_work(path):
    assert not any(name.startswith("acervo.jobs") for name in imports_of(path)), path


@pytest.mark.parametrize(
    "path", modules_under("api") + modules_under("services"), ids=lambda path: path.name
)
def test_only_the_repository_reaches_the_database(path):
    offenders = {name for name in imports_of(path) if name.startswith("acervo.db")}
    assert not offenders, f"{path} imports {sorted(offenders)}; go through acervo.repository"


def test_the_admin_cli_writes_through_the_repository_too():
    assert not any(name.startswith("acervo.db") for name in imports_of(PACKAGE / "admin.py"))
