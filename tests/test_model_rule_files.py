"""The shipped model rules load, select the intended functions, and need neither a key nor the network.

`jev-lint review --dry-run` plans a run without asking the model, so these tests judge the matchers (which subjects
each rule would ask about) and nothing else. Whether the model judges those subjects well is not tested here; that is
what each rule's eval fixtures and baseline.json record, and `jev-lint eval --replay` re-scores them without a key.
The rules stay advisory.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.runtime import REPO_ROOT

RULES = REPO_ROOT / "agents/hooks/lint/model-rules"
RULE_IDS = {"command-query-naming", "error-message-names-operation", "known-defect-marker-names-removal"}

pytestmark = pytest.mark.skipif(shutil.which("jev-lint") is None, reason="jev-lint is not on PATH")

PYTHON_SOURCE = """\
import pytest


def get_user(users):
    users.clear()
    return users


def load(path):
    if not path:
        raise ValueError("bad")
    return path


def pure(a, b):
    return a + b


# Removed when the parser handles empty input (#123).
@pytest.mark.xfail(strict=True, reason="empty input")
def test_known_defect():
    assert False
"""

TYPESCRIPT_SOURCE = """\
function getUser(users: string[]): string[] {
  users.length = 0;
  return users;
}

function load(path: string): string {
  if (!path) {
    throw new Error("bad");
  }
  return path;
}

function pure(a: number, b: number): number {
  return a + b;
}

// Removed when the parser handles empty input (#123).
test.fails("known defect", () => {});
"""


GO_SOURCE = """\
package sample

import (
	"errors"
	"testing"
)

func GetUser(users []string) []string {
	users = users[:0]
	return users
}

func Load(path string) (string, error) {
	if path == "" {
		return "", errors.New("bad")
	}
	return path, nil
}

func Pure(a, b int) int {
	return a + b
}

func TestLoad(t *testing.T) {
	// Removed when the parser handles empty input (#123).
	t.Skip("known defect")
}

func TestBare(t *testing.T) {
	// broken
	t.SkipNow()
}

func (s *Suite) TestSuiteSkip() {
	s.T().Skip("broken")
}

func (c *Client) TestEnabled() bool {
	c.enabled = true
	return c.enabled
}
"""

RUST_SOURCE = """\
use anyhow::{bail, Context, Result};

pub fn get_user(users: &mut Vec<String>) -> usize {
    users.clear();
    users.len()
}

pub fn load(path: &str) -> Result<String> {
    if path.is_empty() {
        bail!("bad");
    }
    Ok(path.to_string())
}

pub fn pure(a: i32, b: i32) -> i32 {
    a + b
}

pub fn read(path: &str) -> Result<String> {
    std::fs::read_to_string(path).context("failed")
}

pub fn qualify(path: &str) -> anyhow::Result<String> {
    if path.is_empty() {
        anyhow::bail!("bad");
    }
    Ok(path.to_string())
}

#[cfg(not(test))]
pub fn get_connection(pool: &mut Vec<u8>) -> usize {
    pool.clear();
    pool.len()
}

// Removed when the parser handles empty input (#123).
#[test]
/* regression */
#[ignore]
fn known_defect() {
    assert_eq!(1, 2);
}

#[test]
#[cfg_attr(target_os = "windows", ignore = "broken")]
fn conditional_defect() {
    assert_eq!(1, 2);
}

#[test]
#[cfg_attr(
    target_os = "windows",
    ignore = "broken"
)]
fn wrapped_defect() {
    assert_eq!(1, 2);
}

#[cfg_attr(target_os = "linux", test)]
fn get_conditional_test(pool: &mut Vec<u8>) {
    pool.clear();
}

#[test]
#[cfg_attr(feature = "ignore", should_panic)]
fn feature_named_ignore() {
    assert_eq!(1, 1);
}

#[cfg_attr(ignore, test)]
fn condition_named_ignore() {
    assert_eq!(1, 1);
}
"""


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for arguments in (
        ["init", "--quiet", "-b", "main"],
        ["config", "user.email", "test@example.invalid"],
        ["config", "user.name", "Test"],
        ["config", "commit.gpgsign", "false"],
    ):
        git(root, *arguments)
    (root / "README.md").write_text("start\n")
    git(root, "add", "README.md")
    git(root, "commit", "--quiet", "-m", "start")
    return root


def plan(root: Path, base: str | None = None) -> dict:
    """The dry-run plan of one review: of the commits since `base`, or without one of the uncommitted changes."""
    selection = ["--base", base] if base else []
    result = subprocess.run(
        ["jev-lint", "review", "--json", "--dry-run", "--no-config", "-c", "none", *selection, "-R", str(RULES)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def subjects_by_rule(report: dict) -> dict[str, int]:
    return {entry["rule"]: entry["subjects"] for entry in report["byRule"] if entry["subjects"]}


def test_every_model_rule_loads_without_an_error() -> None:
    result = subprocess.run(
        ["jev-lint", "rules", "--no-config", "-R", str(RULES)], check=True, capture_output=True, text=True, timeout=60
    )

    assert "0 error(s)" in result.stdout
    assert RULE_IDS <= {line.split("/")[-1] for line in result.stdout.splitlines() if "/" in line and " " not in line}


def test_every_saved_eval_baseline_still_scores_as_accepted() -> None:
    """A moved fixture line, an edited cutoff or criteria, or a stale exemption fails the replay; no key is needed."""
    result = subprocess.run(
        ["jev-lint", "eval", "--replay", "--no-config", "--no-color", str(RULES)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_python_rules_select_the_functions_they_ask_about(repository: Path) -> None:
    (repository / "sample.py").write_text(PYTHON_SOURCE)

    counts = subjects_by_rule(plan(repository))

    # Four functions; only `load` raises; only the decorated test carries a known-defect marker.
    assert counts == {
        "command-query-naming": 4,
        "error-message-names-operation": 1,
        "known-defect-marker-names-removal": 1,
    }


def test_typescript_rules_select_the_functions_they_ask_about(repository: Path) -> None:
    (repository / "sample.ts").write_text(TYPESCRIPT_SOURCE)

    counts = subjects_by_rule(plan(repository))

    assert counts == {
        "command-query-naming": 3,
        "error-message-names-operation": 1,
        "known-defect-marker-names-removal": 1,
    }


def test_go_rules_select_the_functions_they_ask_about(repository: Path) -> None:
    (repository / "sample_test.go").write_text(GO_SOURCE)

    counts = subjects_by_rule(plan(repository))

    # Three functions are named for a read or an effect, plus the production method `TestEnabled` and the suite method
    # `TestSuiteSkip`, which are not top-level functions taking `*testing.T`; `TestLoad` and `TestBare` are named for
    # what they verify. Only `Load` builds an error; three skips carry a known-defect marker: `t.Skip`, `t.SkipNow`
    # and the suite form `s.T().Skip`.
    assert counts == {
        "command-query-naming": 5,
        "error-message-names-operation": 1,
        "known-defect-marker-names-removal": 3,
    }


def test_rust_rules_select_the_functions_they_ask_about(repository: Path) -> None:
    (repository / "sample.rs").write_text(RUST_SOURCE)

    counts = subjects_by_rule(plan(repository))

    # `known_defect` carries `#[test]` before `#[ignore]` and two comments, so it is not asked about by name; the
    # `#[cfg(not(test))]` function is production code and is. `read` builds its message with `.context(..)` and
    # `qualify` with the path-qualified `anyhow::bail!`. Two of the three ignores are `cfg_attr`, one of them wrapped
    # over several lines as rustfmt writes it. `cfg_attr` whose condition merely names `ignore` is not an ignore.
    assert counts == {
        "command-query-naming": 6,
        "error-message-names-operation": 3,
        "known-defect-marker-names-removal": 3,
    }


@pytest.mark.parametrize("language", ["go", "rust"])
def test_every_go_and_rust_rule_ships_an_eval_suite_with_both_kinds_of_fixture(language: str) -> None:
    result = subprocess.run(
        ["jev-lint", "eval", "--dry-run", "--no-config", str(RULES / language)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )

    suites = [line for line in result.stdout.splitlines() if line.startswith(f"{language}/")]
    assert {line.split(":")[0] for line in suites} == {f"{language}/{rule_id}" for rule_id in RULE_IDS}
    for rule_id in RULE_IDS:
        fixtures = (RULES / language / rule_id / "fixtures").iterdir()
        names = {path.name for path in fixtures}
        assert {name.split(".")[0].removesuffix("_test") for name in names} == {"violating", "conforming"}


def test_functions_committed_since_the_base_are_still_selected(repository: Path) -> None:
    base = git(repository, "rev-parse", "HEAD")
    (repository / "sample.py").write_text(PYTHON_SOURCE)
    git(repository, "add", "sample.py")
    git(repository, "commit", "--quiet", "-m", "add sample")

    assert subjects_by_rule(plan(repository, base))["error-message-names-operation"] == 1


def test_committed_functions_are_not_selected_by_the_review_of_uncommitted_changes(repository: Path) -> None:
    (repository / "sample.py").write_text(PYTHON_SOURCE)
    git(repository, "add", "sample.py")
    git(repository, "commit", "--quiet", "-m", "add sample")
    (repository / "other.py").write_text("def unrelated():\n    return 1\n")

    assert subjects_by_rule(plan(repository)) == {"command-query-naming": 1}


def test_uncommitted_and_untracked_changes_are_not_selected_by_the_review_of_commits(repository: Path) -> None:
    """With a base, `jev-lint review` judges `base...HEAD` only: this is why a session needs both reviews."""
    base = git(repository, "rev-parse", "HEAD")
    (repository / "sample.py").write_text(PYTHON_SOURCE)
    git(repository, "add", "sample.py")
    (repository / "untracked.py").write_text(PYTHON_SOURCE)

    assert subjects_by_rule(plan(repository, base)) == {}
