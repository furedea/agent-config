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
    "go_no_vague_directory_name": ["util/user.go", "internal/util/user.go", "common/user.go"],
    "py_async_test_anyio_marker": ["test_user.py", "tests/user_test.py", "tests/conftest.py"],
}
CLEAN_PATHS = {
    "go_no_vague_directory_name": [
        "user_store.go",
        "util.go",
        "pkg/store/user.go",
        "internal/store/user.go",
        "internal/package/user.go",
    ],
    "py_async_test_anyio_marker": ["user.py", "tests/helpers.py", "src/pkg/testing_utils.py"],
}
SOURCE_BY_SUFFIX = {".go": "package a\n", ".py": "async def test_user():\n    pass\n"}


def require_ast_grep() -> str:
    executable = shutil.which("ast-grep")
    if executable is None:
        reason = "ast-grep is provided by the flake dev shell"
        if os.environ.get("REQUIRE_AST_GREP") == "1":
            pytest.fail(reason)
        pytest.skip(reason)
    return executable


def test_every_file_scoped_rule_has_flagged_and_clean_paths() -> None:
    assert sorted(FLAGGED_PATHS) == FILE_SCOPED_RULE_IDS
    assert sorted(CLEAN_PATHS) == FILE_SCOPED_RULE_IDS


def test_file_scoped_rules_flag_exactly_the_vaguely_named_paths(tmp_path: Path) -> None:
    executable = require_ast_grep()
    for rule_id in FILE_SCOPED_RULE_IDS:
        for relative in FLAGGED_PATHS[rule_id] + CLEAN_PATHS[rule_id]:
            (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / relative).write_text(SOURCE_BY_SUFFIX[Path(relative).suffix])

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
    assert flagged == {rule_id: set(FLAGGED_PATHS[rule_id]) for rule_id in FILE_SCOPED_RULE_IDS}, result.stderr


def test_directories_above_the_repository_do_not_change_what_the_hook_flags(tmp_path: Path) -> None:
    require_ast_grep()
    static_rule_scan = load_script_module("agents/hooks/lint_format.py", "lint_format_for_ancestors").static_rule_scan
    repository = tmp_path.joinpath("common", "pkg", "util", "tests", "repo")
    clean, flagged = repository / "src/user.go", repository / "util/user.go"
    for path in (clean, flagged):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("package a\n")
    (repository / ".git").mkdir()

    messages = static_rule_scan.diagnostics([clean, flagged])

    assert [message.split("\n")[0] for message in messages] == [
        f"Static rule go_no_vague_directory_name · {flagged}:1"
    ]


def test_a_project_without_git_is_matched_from_its_manifest_directory(tmp_path: Path) -> None:
    require_ast_grep()
    static_rule_scan = load_script_module("agents/hooks/lint_format.py", "lint_format_for_manifests").static_rule_scan
    project = tmp_path / "common" / "project"
    flagged = project / "util" / "user.go"
    flagged.parent.mkdir(parents=True)
    flagged.write_text("package a\n")
    (project / "go.mod").write_text("module example.com/project\n")

    messages = static_rule_scan.diagnostics([flagged])

    assert [message.split("\n")[0] for message in messages] == [
        f"Static rule go_no_vague_directory_name · {flagged}:1"
    ]


def test_a_file_name_that_looks_like_an_option_is_scanned_as_a_path(tmp_path: Path) -> None:
    require_ast_grep()
    static_rule_scan = load_script_module("agents/hooks/lint_format.py", "lint_format_for_options").static_rule_scan
    (tmp_path / ".git").mkdir()
    option_like = tmp_path / "-U.go"
    option_like.write_text("package a\n")

    assert static_rule_scan.diagnostics([option_like]) == ()
    assert option_like.read_text() == "package a\n"


NOTE_PATTERN = re.compile(r"^note:\s*\S", re.MULTILINE)
ERROR_PATTERN = re.compile(r"^severity:\s*error\s*$", re.MULTILINE)


@pytest.mark.parametrize(
    "rule_file",
    [path for path in RULE_FILES if ERROR_PATTERN.search(path.read_text())],
    ids=lambda path: path.stem,
)
def test_blocking_rule_states_its_fix_in_a_note(rule_file: Path) -> None:
    assert NOTE_PATTERN.search(rule_file.read_text())
