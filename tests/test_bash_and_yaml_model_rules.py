"""The bash-style and github-actions-style model rules select the code they ask about, without a key or the network.

`jev-lint review --dry-run` plans a run without asking the model, so these tests judge the matchers only. The model's
judgement is advisory (ADR-0027) and is recorded by each rule's eval fixtures, not here.
"""

import json
import subprocess
from pathlib import Path

import pytest

from tests.runtime import REPO_ROOT

RULES = REPO_ROOT / "agents/hooks/lint/model-rules"

pytestmark = pytest.mark.needs_jev_lint

WORKFLOW = ".github/workflows/ci.yml"


def subject_count(root: Path, rule: str) -> int:
    """How many subjects of `rule` a review of the uncommitted files in `root` would ask about."""
    result = subprocess.run(
        ["jev-lint", "review", "--json", "--dry-run", "--no-config", "-c", "none", "-R", str(RULES)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return sum(entry["subjects"] for entry in json.loads(result.stdout)["byRule"] if entry["rule"] == rule)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for arguments in (
        ["init", "--quiet", "-b", "main"],
        ["config", "user.email", "test@example.invalid"],
        ["config", "user.name", "Test"],
        ["config", "commit.gpgsign", "false"],
        ["commit", "--quiet", "--allow-empty", "-m", "start"],
    ):
        subprocess.run(["git", *arguments], cwd=root, check=True)
    return root


def write(root: Path, name: str, source: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)


@pytest.mark.parametrize(
    ("rule", "name", "source", "expected"),
    [
        pytest.param(
            "workflow-default-shell",
            WORKFLOW,
            "on: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - {run: make | tee log}\n",
            1,
            id="default-shell-flow-step",
        ),
        pytest.param(
            "workflow-default-shell",
            WORKFLOW,
            "on: push\njobs:\n  build: {runs-on: ubuntu-latest, steps: [{run: make}, {uses: x/y@v1}]}\n",
            1,
            id="default-shell-flow-steps-of-a-flow-job",
        ),
        pytest.param(
            "workflow-default-shell",
            WORKFLOW,
            "on: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: x/y@v1\n        with: {run: make}\n",
            0,
            id="default-shell-not-an-action-input",
        ),
        pytest.param(
            "job-permissions-least-privilege",
            WORKFLOW,
            'on: push\npermissions: read-all\n"jobs":\n  build:\n    runs-on: ubuntu-latest\n'
            "    permissions:\n      contents: write\n    steps:\n      - run: make\n",
            2,
            id="permissions-quoted-jobs-key",
        ),
        pytest.param(
            "job-permissions-least-privilege",
            WORKFLOW,
            "on: push\npermissions: {}\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
            "    permissions: {contents: write}\n    steps:\n      - run: make\n"
            "  test: {runs-on: ubuntu-latest, permissions: {contents: read}, steps: [{run: make}]}\n",
            2,
            id="permissions-of-a-flow-job",
        ),
        pytest.param(
            "job-permissions-least-privilege",
            WORKFLOW,
            "on: push\njobs:\n  test: {runs-on: ubuntu-latest, permissions: {}, steps: [{run: make}]}\n",
            0,
            id="permissions-empty-in-a-flow-job",
        ),
        pytest.param(
            "cache-key-and-trust",
            WORKFLOW,
            "on: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - {uses: actions/cache@v4, with: {path: ~/.npm, key: npm}}\n",
            1,
            id="cache-flow-step",
        ),
        pytest.param(
            "cache-key-and-trust",
            WORKFLOW,
            "on: push\njobs:\n  build: {runs-on: ubuntu-latest, steps: [{uses: actions/cache/restore@v4}]}\n",
            1,
            id="cache-flow-steps-of-a-flow-job",
        ),
        pytest.param(
            "usage-help-and-error-exits",
            "cli.sh",
            '#!/usr/bin/env bash\nif (( $# == 0 )); then\n  echo "missing file" >&2\n  exit 0\nfi\n',
            1,
            id="usage-missing-argument-count",
        ),
        pytest.param(
            "usage-help-and-error-exits",
            "cli.sh",
            '#!/usr/bin/env bash\nif [[ $# -lt 1 ]]; then\n  echo "missing file"\n  exit 1\nfi\n',
            1,
            id="usage-missing-argument-count-test",
        ),
        pytest.param(
            "usage-help-and-error-exits",
            "cli.sh",
            "#!/usr/bin/env bash\nwhile getopts h opt; do\n  case $opt in\n    h) echo help ;;\n  esac\ndone\n",
            1,
            id="usage-getopts-bare-h-label",
        ),
        pytest.param(
            "usage-help-and-error-exits",
            "cli.sh",
            '#!/usr/bin/env bash\ncase "$mode" in\n  fast) run_fast ;;\nesac\n',
            0,
            id="usage-unrelated-case",
        ),
        pytest.param(
            "function-variables-local-near-use",
            "lib.sh",
            '#!/usr/bin/env bash\ncount_up() {\n  : "$((count++))"\n}\n',
            1,
            id="local-arithmetic-expansion-assignment",
        ),
        pytest.param(
            "function-variables-local-near-use",
            "lib.sh",
            '#!/usr/bin/env bash\nshow() {\n  echo "$((1 + 2))"\n}\n',
            0,
            id="local-arithmetic-expansion-without-assignment",
        ),
    ],
)
def test_rule_selects_the_code_it_asks_about(
    repository: Path, rule: str, name: str, source: str, expected: int
) -> None:
    write(repository, name, source)

    assert subject_count(repository, rule) == expected
