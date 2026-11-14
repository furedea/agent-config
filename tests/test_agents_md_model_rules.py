"""The model rules migrated from agents/AGENTS.md select the functions they ask about, without a key or the network.

`jev-lint review --dry-run` plans a run without asking the model, so these tests judge the matchers only. The model's
judgement is advisory (ADR-0021) and is not tested here.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.runtime import REPO_ROOT

RULES = REPO_ROOT / "agents/hooks/lint/model-rules"
RULE_IDS = (
    "function-single-purpose",
    "construction-separate-from-execution",
    "no-reaching-through-collaborators",
    "no-comment-restating-code",
    "no-exposed-mutable-collection",
)

pytestmark = pytest.mark.skipif(shutil.which("jev-lint") is None, reason="jev-lint is not on PATH")

SAMPLES = {
    "python": (
        "sample.py",
        """\
class Box:
    def items(self):
        return self._items

    def total(self):
        # add them up
        return sum(self._items)

    def city(self, order):
        return order.customer.address.city.upper()


def plain(a, b):
    return a + b


def fail():
    raise ValueError("bad")


def run(path):
    client = Client(path)
    client.connect()
    rows = client.read()
    total = 0
    for row in rows:
        total += row
    client.flush()
    client.close()
    return total
""",
    ),
    "typescript": (
        "sample.ts",
        """\
class Box {
  items(): string[] {
    return this.list;
  }

  total(): number {
    // add them up
    return this.list.length;
  }

  city(order: Order): string {
    return order.customer.address.city.toUpperCase();
  }
}

function plain(a: number, b: number): number {
  return a + b;
}

const arrow = (a: number): number => a + 1;

function local(): number {
  return new Map<string, number>().size;
}

function run(path: string): number {
  const client = new Client(path);
  client.connect();
  const rows = client.read();
  let total = 0;
  for (const row of rows) {
    total += row;
  }
  return total;
}
""",
    ),
    "go": (
        "sample.go",
        """\
package sample

func (b *Box) Items() []string {
	return b.items
}

func (b *Box) Total() int {
	// add them up
	return len(b.items)
}

func City(order Order) string {
	return order.Customer.Address.City.String()
}

func Plain(a, b int) int {
	return a + b
}

func Fail() error {
	return errors.New("bad")
}

func Run(path string) int {
	client := NewClient(path)
	client.Connect()
	rows := client.Read()
	total := 0
	for _, row := range rows {
		total += row
	}
	return total
}
""",
    ),
    "rust": (
        "sample.rs",
        """\
impl Box {
    pub fn items(&mut self) -> &mut Vec<String> {
        &mut self.items
    }

    pub fn total(&self) -> usize {
        // add them up
        self.items.len()
    }

    pub fn city(order: &Order) -> String {
        order.customer.address.city.to_uppercase()
    }
}

pub fn plain(a: i32, b: i32) -> i32 {
    a + b
}

pub fn local() -> usize {
    Vec::<i32>::new().len()
}

pub fn run(path: &str) -> i32 {
    let client = Client::new(path);
    client.connect();
    let rows = client.read();
    let mut total = 0;
    for row in rows {
        total += row;
    }
    total
}
""",
    ),
}

# Standard collections and errors (`ValueError`, `new Map`, `errors.New`, `Vec::new`) are not constructions.
# Each sample has three methods, a plain function, and `run`, the only function of ten lines or more and the only one
# that constructs an object (TypeScript adds an arrow function bound to a name, which no rule selects here). Only
# `items` returns its own collection, only `total` has a comment, only `city` chains three member accesses into a call.
EXPECTED = {
    "function-single-purpose": 1,
    "construction-separate-from-execution": 1,
    "no-reaching-through-collaborators": 1,
    "no-comment-restating-code": 1,
    "no-exposed-mutable-collection": 1,
}


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
        subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)
    (root / "README.md").write_text("start\n")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "start"], cwd=root, check=True, capture_output=True)
    return root


@pytest.mark.parametrize("language", sorted(SAMPLES))
def test_each_rule_selects_the_functions_it_asks_about(language: str, repository: Path) -> None:
    name, source = SAMPLES[language]
    (repository / name).write_text(source)

    result = subprocess.run(
        ["jev-lint", "review", "--json", "--dry-run", "--no-config", "-c", "none", "-R", str(RULES)],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    report = json.loads(result.stdout)
    counts = {entry["rule"]: entry["subjects"] for entry in report["byRule"] if entry["rule"] in RULE_IDS}

    assert {rule: counts.get(rule, 0) for rule in RULE_IDS} == EXPECTED
