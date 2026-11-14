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

type Request = { readonly url: string; readonly retries?: number };

const parsed = JSON.parse("{}") as Request;
const levels = ["low", "high"] as const;
const typed = <Request>JSON.parse("{}");

function stamp(): number {
  // The clock is read here on purpose.
  return Date.now();
}

describe("stamp", () => {
  it("returns a number", () => {});
});

describe.concurrent("stamp again", () => {
  it("returns a number", () => {});
});

vi.mock("./sibling");
vi.doMock("./other");

it.concurrent("first case", () => {});
it.concurrent("second case", () => {});

const expiresAt = () => Date.now() + 1000;

class Loader {
  load = (path: string): string => {
    if (!path) {
      throw new Error("missing");
    }
    return path;
  };
}

const loadLater = function (path: string): string {
  if (!path) {
    throw new Error("missing");
  }
  return path;
};
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

#[cfg_attr(feature = "tokio", tokio::test(flavor = "multi_thread"))]
fn argumented_conditional_test() {
    assert_eq!(1, 1);
}

#[cfg_attr(
    feature = "tokio",
    tokio::test(flavor = "multi_thread")
)]
fn wrapped_argumented_test() {
    assert_eq!(1, 1);
}

#[cfg_attr(any(unix, ignore = "ci"), should_panic)]
fn nested_condition_names_ignore() {
    assert_eq!(1, 1);
}

#[test]
#[cfg_attr(unix, ignore)]
fn bare_conditional_ignore() {
    assert_eq!(1, 2);
}

pub fn lookup(map: &Map, key: &str) -> Result<u8, &'static str> {
    map.get(key).ok_or("missing")
}

pub fn lookup_named(map: &Map, key: &str) -> Result<u8, String> {
    map.get(key).ok_or_else(|| format!("read {key}: missing"))
}

pub fn convert(raw: &str) -> Result<u8, String> {
    raw.parse().map_err(|e| format!("parse {raw}: {e}"))
}

pub fn keep_error(map: &Map, key: &str, err: Error) -> Result<u8, Error> {
    map.get(key).ok_or(err)
}

pub fn convert_plain(raw: &str) -> Result<u8, Error> {
    raw.parse().map_err(From::from)
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


def recorded_files(node: object) -> list[str]:
    """Every `file` value in a saved eval record, wherever it sits."""
    if isinstance(node, dict):
        own = [node["file"]] if isinstance(node.get("file"), str) else []
        return own + [path for value in node.values() for path in recorded_files(value)]
    if isinstance(node, list):
        return [path for value in node for path in recorded_files(value)]
    return []


def test_no_saved_eval_baseline_records_an_absolute_path() -> None:
    """An absolute path names one checkout's directory; a baseline is relocated on load only from a relative one."""
    baselines = sorted(RULES.glob("*/*/baseline.json"))
    assert baselines

    absolute = {
        f"{baseline.relative_to(RULES)}: {path}"
        for baseline in baselines
        for path in recorded_files(json.loads(baseline.read_text()))
        if Path(path).is_absolute()
    }

    assert not absolute, "\n".join(sorted(absolute))


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

    # `stamp` is a fourth function and the only one that holds a comment, and the comment above `test.fails` stands
    # outside any function; `stamp` and the arrow function `expiresAt` read the clock; `as const` is not an
    # assertion to judge, and the angle-bracket form `<Request>` has its own rule; `load`, the field arrow function
    # `Loader.load` and the function expression `loadLater` throw; the `describe` and `describe.concurrent` blocks
    # and the top level of the file, which holds two `it.concurrent` calls, are the groups of tests; `vi.mock` and
    # `vi.doMock` are both mocks.
    assert counts == {
        "angle-bracket-assertion-follows-validation": 1,
        "command-query-naming": 4,
        "comment-explains-why": 2,
        "error-message-names-operation": 1,
        "expected-failure-returned-as-value": 3,
        "inject-time-and-randomness": 2,
        "known-defect-marker-names-removal": 1,
        "mock-only-external-boundaries": 2,
        "repeated-cases-use-it-each": 3,
        "states-modeled-as-discriminated-union": 1,
        "type-assertion-follows-validation": 1,
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
    # `qualify` with the path-qualified `anyhow::bail!`. Three of the four ignores are `cfg_attr`: one wrapped over
    # several lines as rustfmt writes it, one a bare `ignore` after the condition. `cfg_attr` whose condition merely
    # names `ignore`, also inside `any(..)`, is not an ignore. A `cfg_attr` that attaches a test with arguments
    # (`tokio::test(..)`), wrapped or not, is a test and is left out of the naming rule. `ok_or`, `ok_or_else` and
    # `map_err` select a function only when an argument writes a message (a literal or `format!`), not when it passes
    # an existing error value or `From::from`.
    assert counts == {
        "command-query-naming": 12,
        "error-message-names-operation": 6,
        "known-defect-marker-names-removal": 4,
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
