"""A test that needs jev-lint skips without it, and fails instead when REQUIRE_JEV_LINT=1 (as CI sets it)."""

import os
import subprocess
import sys

from tests.runtime import REPO_ROOT


def run_without_jev_lint(**environment: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key != "REQUIRE_JEV_LINT"} | {"PATH": "/nonexistent"}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-n0", "-p", "no:cacheprovider", "-q", "tests/test_python_model_rules.py"],
        cwd=REPO_ROOT,
        env=env | environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_missing_jev_lint_skips_the_tests_that_need_it() -> None:
    result = run_without_jev_lint()

    assert result.returncode == 0, result.stdout
    assert "skipped" in result.stdout


def test_missing_jev_lint_fails_when_it_is_required() -> None:
    result = run_without_jev_lint(REQUIRE_JEV_LINT="1")

    assert result.returncode != 0
    assert "jev-lint is provided by" in result.stdout
