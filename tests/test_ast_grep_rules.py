"""ast-grep rule contracts: every rule has native valid and invalid cases, and every case behaves as declared."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.runtime import REPO_ROOT, load_script_module

LINT_ROOT = REPO_ROOT / "agents/hooks/lint"
SG_CONFIG = LINT_ROOT / "sgconfig.yml"
FILE_SCOPED_PATTERN = re.compile(r"^files:", re.MULTILINE)
RULE_FILES = sorted((LINT_ROOT / "rules").glob("*/*.yml"))
SNIPPET_RULE_FILES = [path for path in RULE_FILES if not FILE_SCOPED_PATTERN.search(path.read_text())]
FILE_SCOPED_RULE_IDS = sorted(path.stem for path in RULE_FILES if path not in SNIPPET_RULE_FILES)
CASE_DIRECTORY = LINT_ROOT / "rule-tests"
ID_PATTERN = re.compile(r"^id:\s*(\S+)\s*$", re.MULTILINE)
CASE_SECTION_PATTERN = re.compile(r"^(valid|invalid):\s*\n\s+- ", re.MULTILINE)


@pytest.mark.parametrize("rule_file", RULE_FILES, ids=lambda path: path.stem)
def test_rule_file_is_named_after_its_id(rule_file: Path) -> None:
    assert ID_PATTERN.findall(rule_file.read_text()) == [rule_file.stem]


@pytest.mark.parametrize("rule_file", SNIPPET_RULE_FILES, ids=lambda path: path.stem)
def test_rule_has_at_least_one_valid_and_one_invalid_case(rule_file: Path) -> None:
    case_file = CASE_DIRECTORY / rule_file.name

    assert case_file.is_file()
    assert ID_PATTERN.findall(case_file.read_text()) == [rule_file.stem]
    assert set(CASE_SECTION_PATTERN.findall(case_file.read_text())) == {"valid", "invalid"}


def test_every_case_file_belongs_to_a_rule() -> None:
    rule_names = {path.name for path in RULE_FILES}

    assert sorted(path.name for path in CASE_DIRECTORY.glob("*.yml") if path.name not in rule_names) == []


def test_ast_grep_accepts_every_valid_case_and_reports_every_invalid_case() -> None:
    executable = shutil.which("ast-grep")
    if executable is None:
        reason = "ast-grep is provided by the flake dev shell"
        if os.environ.get("REQUIRE_AST_GREP") == "1":
            pytest.fail(reason)
        pytest.skip(reason)

    result = subprocess.run(
        [executable, "test", "--config", str(SG_CONFIG), "--skip-snapshot-tests"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


# Snippet tests carry no path, so a rule scoped by `files:` is exercised by scanning named files.
FLAGGED_PATHS = {
    "ts_no_vague_file_name": [
        "utils.ts",
        "src/string_utils.ts",
        "string.utils.ts",
        "widget.test.utils.ts",
        "helper-x.ts",
    ],
    "tsx_no_vague_file_name": ["utils.tsx", "button.helpers.tsx"],
    "py_no_vague_file_name": ["utils.py", "pkg/string_utils.py", "user_manager.py"],
    "rs_no_vague_file_name": ["utils.rs", "src/string_helpers.rs", "tests/common_setup.rs"],
    "go_no_vague_file_name": [
        "utils.go",
        "string_utils.go",
        "pkg/store/user.go",
        "internal/util/user.go",
        "common/user.go",
    ],
}
CLEAN_PATHS = {
    "ts_no_vague_file_name": ["utility.ts", "futile.ts", "user_store.ts", "utils.py"],
    "tsx_no_vague_file_name": ["button.tsx", "utility.tsx"],
    "py_no_vague_file_name": ["__init__.py", "user_store.py", "futile.py", "__common__.py"],
    "rs_no_vague_file_name": ["user_store.rs", "tests/common/mod.rs", "tests/common/setup.rs"],
    "go_no_vague_file_name": ["user_store.go", "futile.go", "internal/store/user.go", "internal/package/user.go"],
}
SOURCE_TEXT = {
    ".ts": "export const a = 1\n",
    ".tsx": "export const a = 1\n",
    ".py": "a = 1\n",
    ".rs": "fn a() {}\n",
    ".go": "package a\n",
}


def test_every_file_scoped_rule_has_flagged_and_clean_paths() -> None:
    assert sorted(FLAGGED_PATHS) == FILE_SCOPED_RULE_IDS
    assert sorted(CLEAN_PATHS) == FILE_SCOPED_RULE_IDS


def test_file_scoped_rules_flag_exactly_the_vaguely_named_files(tmp_path: Path) -> None:
    executable = shutil.which("ast-grep")
    if executable is None:
        reason = "ast-grep is provided by the flake dev shell"
        if os.environ.get("REQUIRE_AST_GREP") == "1":
            pytest.fail(reason)
        pytest.skip(reason)

    expected: dict[str, set[str]] = {}
    for rule_id in FILE_SCOPED_RULE_IDS:
        for relative in FLAGGED_PATHS[rule_id] + CLEAN_PATHS[rule_id]:
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(SOURCE_TEXT[path.suffix])
        expected[rule_id] = set(FLAGGED_PATHS[rule_id])

    result = subprocess.run(
        [executable, "scan", "--config", str(SG_CONFIG), "--json=compact", "."],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )

    flagged: dict[str, set[str]] = {rule_id: set() for rule_id in FILE_SCOPED_RULE_IDS}
    for hit in json.loads(result.stdout):
        if hit["ruleId"] in flagged:
            flagged[hit["ruleId"]].add(Path(hit["file"]).as_posix().removeprefix("./"))
    assert flagged == expected, result.stderr


ANCESTOR_SEGMENTS = ("common", "pkg", "util", "tests")


def test_directories_above_the_repository_do_not_change_what_the_hook_flags(tmp_path: Path) -> None:
    executable = shutil.which("ast-grep")
    if executable is None:
        reason = "ast-grep is provided by the flake dev shell"
        if os.environ.get("REQUIRE_AST_GREP") == "1":
            pytest.fail(reason)
        pytest.skip(reason)
    static_rule_scan = load_script_module("agents/hooks/lint_format.py", "lint_format_for_ancestors").static_rule_scan
    repository = tmp_path.joinpath(*ANCESTOR_SEGMENTS, "common", "repo")
    for relative, text in {
        "src/user.go": "package a\n",
        "src/user.rs": "fn a() {}\n",
        "src/utils.rs": "fn a() {}\n",
    }.items():
        (repository / relative).parent.mkdir(parents=True, exist_ok=True)
        (repository / relative).write_text(text)
    (repository / ".git").mkdir()

    messages = static_rule_scan.diagnostics(
        [repository / "src/user.go", repository / "src/user.rs", repository / "src/utils.rs"]
    )

    assert [(m.split(" · ")[0], m.split(" · ")[1].split(":")[0]) for m in messages] == [
        ("Static rule rs_no_vague_file_name", str(repository / "src/utils.rs"))
    ]
