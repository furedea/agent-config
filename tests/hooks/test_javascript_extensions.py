"""Module-flavored JavaScript and TypeScript files are verified like .js and .ts files."""

import json
from pathlib import Path

import pytest

from tests.runtime import REPO_ROOT, load_script_module

selection = load_script_module("agents/hooks/lib/check_selection.py", "check_selection")

DEFAULTS = REPO_ROOT / "agents/hooks/rules/related_test_defaults.json"


@pytest.mark.parametrize("suffix", [".mts", ".cts", ".mjs", ".cjs"])
def test_module_flavored_sources_and_tests_are_verified(tmp_path: Path, suffix: str) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "devDependencies": {"vitest": "1"}})
    )
    for name in (f"src/app{suffix}", f"tests/app.test{suffix}", f"src/other{suffix}"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    commands, errors = selection.language_plan(
        tmp_path, selection.load_defaults(DEFAULTS), (f"src/app{suffix}", f"src/other{suffix}")
    )
    assert not errors
    assert [item.arguments for item in commands] == [
        ("pnpm", "exec", "vitest", "run", f"tests/app.test{suffix}"),
        (
            "pnpm",
            "exec",
            "vitest",
            "related",
            "--run",
            "--passWithNoTests",
            f"src/app{suffix}",
            f"src/other{suffix}",
        ),
    ]
