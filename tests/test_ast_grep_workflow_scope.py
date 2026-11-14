"""Workflow rules apply to a workflow file named by absolute path, as the lint hook passes it."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.runtime import REPO_ROOT

SG_CONFIG = REPO_ROOT / "agents/hooks/lint/sgconfig.yml"
UNSAFE_WORKFLOW = """\
on:
  pull_request:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd
      - run: echo hi
"""
WORKFLOW_RULES = {
    "gha_workflow_permissions_deny_all",
    "gha_workflow_default_shell",
    "gha_workflow_concurrency",
    "gha_job_timeout_minutes",
    "gha_pinned_uses_version_comment",
}


def scan(path: Path) -> set[str]:
    executable = shutil.which("ast-grep")
    if executable is None:
        if os.environ.get("REQUIRE_AST_GREP") == "1":
            pytest.fail("ast-grep is provided by the flake dev shell")
        pytest.skip("ast-grep is provided by the flake dev shell")
    result = subprocess.run(
        [executable, "scan", "--config", str(SG_CONFIG), "--json=stream", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return {json.loads(line)["ruleId"] for line in result.stdout.splitlines() if line.strip()}


def test_workflow_rules_report_a_workflow_named_by_absolute_path(tmp_path: Path) -> None:
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(UNSAFE_WORKFLOW)

    assert scan(workflow) >= WORKFLOW_RULES


def test_workflow_rules_skip_a_yaml_file_outside_the_workflow_directory(tmp_path: Path) -> None:
    other = tmp_path / "config/ci.yml"
    other.parent.mkdir(parents=True)
    other.write_text(UNSAFE_WORKFLOW)

    assert scan(other) & WORKFLOW_RULES == set()
