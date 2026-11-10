"""ast-grep rule contracts: every rule has native valid and invalid cases, and every case behaves as declared."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.runtime import REPO_ROOT

LINT_ROOT = REPO_ROOT / "agents/hooks/lint"
SG_CONFIG = LINT_ROOT / "sgconfig.yml"
RULE_FILES = sorted((LINT_ROOT / "rules").glob("*/*.yml"))
CASE_DIRECTORY = LINT_ROOT / "rule-tests"
ID_PATTERN = re.compile(r"^id:\s*(\S+)\s*$", re.MULTILINE)
CASE_SECTION_PATTERN = re.compile(r"^(valid|invalid):\s*\n\s+- ", re.MULTILINE)


@pytest.mark.parametrize("rule_file", RULE_FILES, ids=lambda path: path.stem)
def test_rule_file_is_named_after_its_id(rule_file: Path) -> None:
    assert ID_PATTERN.findall(rule_file.read_text()) == [rule_file.stem]


@pytest.mark.parametrize("rule_file", RULE_FILES, ids=lambda path: path.stem)
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
