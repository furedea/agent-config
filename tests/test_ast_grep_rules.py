"""ast-grep rule contracts: every rule has valid and invalid cases, and every case behaves as declared."""

import json
from pathlib import Path
import re
import subprocess

import pytest

from tests.runtime import REPO_ROOT


LINT_ROOT = REPO_ROOT / "agents/lint"
SG_CONFIG = LINT_ROOT / "sgconfig.yml"
RULE_FILES = sorted((LINT_ROOT / "rules").glob("*/*.yml"))
CASE_DIRECTORY = REPO_ROOT / "tests/ast-grep"
ID_PATTERN = re.compile(r"^id:\s*(\S+)\s*$", re.MULTILINE)
CASE_SECTION_PATTERN = re.compile(r"^(valid|invalid):\s*\n\s+- ", re.MULTILINE)
EXAMPLE_SECTION_PATTERN = re.compile(r"^  (conforming|violating):\s*$")
EXAMPLE_START_PATTERN = re.compile(r"^    - \|\s*$")
EXAMPLE_INDENT = " " * 6
INITIAL_RULE_COUNT = 10


def test_registry_holds_the_initial_ast_grep_rules() -> None:
    assert len(RULE_FILES) >= INITIAL_RULE_COUNT


@pytest.mark.parametrize("rule_file", RULE_FILES, ids=lambda path: path.stem)
def test_rule_file_is_named_after_its_id_and_declares_the_ast_grep_method(rule_file: Path) -> None:
    text = rule_file.read_text()

    assert ID_PATTERN.findall(text) == [rule_file.stem]
    assert re.search(r"^method:\s*ast-grep\s*$", text, re.MULTILINE)


@pytest.mark.parametrize("rule_file", RULE_FILES, ids=lambda path: path.stem)
def test_rule_has_at_least_one_valid_and_one_invalid_case(rule_file: Path) -> None:
    case_file = CASE_DIRECTORY / rule_file.name

    assert case_file.is_file()
    assert ID_PATTERN.findall(case_file.read_text()) == [rule_file.stem]
    assert set(CASE_SECTION_PATTERN.findall(case_file.read_text())) == {"valid", "invalid"}


def test_every_case_file_belongs_to_a_rule() -> None:
    rule_names = {path.name for path in RULE_FILES}

    assert sorted(path.name for path in CASE_DIRECTORY.glob("*.yml") if path.name not in rule_names) == []


@pytest.mark.parametrize("rule_file", RULE_FILES, ids=lambda path: path.stem)
def test_registry_examples_agree_with_the_rule(rule_file: Path) -> None:
    examples = _registry_examples(rule_file.read_text())

    assert examples["conforming"] and examples["violating"]
    assert [code for code in examples["conforming"] if _findings(rule_file, code)] == []
    assert [code for code in examples["violating"] if not _findings(rule_file, code)] == []


def test_ast_grep_accepts_every_valid_case_and_reports_every_invalid_case() -> None:
    result = subprocess.run(
        ["ast-grep", "test", "--config", str(SG_CONFIG), "--skip-snapshot-tests"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def _registry_examples(rule_text: str) -> dict[str, list[str]]:
    examples: dict[str, list[str]] = {"conforming": [], "violating": []}
    kind: str | None = None
    block: list[str] | None = None
    for line in rule_text.splitlines():
        if line and not line.startswith(" "):
            kind, block = None, None
        elif (section := EXAMPLE_SECTION_PATTERN.match(line)) is not None:
            kind, block = section.group(1), None
        elif kind is not None and EXAMPLE_START_PATTERN.match(line):
            block = []
            examples[kind].append("")
            continue
        if kind is not None and block is not None and (not line or line.startswith(EXAMPLE_INDENT)):
            block.append(line[len(EXAMPLE_INDENT) :])
            examples[kind][-1] = "\n".join(block)
        elif block is not None:
            block = None
    return examples


def _findings(rule_file: Path, code: str) -> list[object]:
    result = subprocess.run(
        ["ast-grep", "scan", "--rule", str(rule_file), "--stdin", "--json=compact"],
        input=code,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)
