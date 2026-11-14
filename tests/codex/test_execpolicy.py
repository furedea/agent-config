"""Check generated rules with Codex's real policy evaluator without executing commands."""

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
from tests.runtime import CliRunner

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def codex_policy(agent_harness: CliRunner, tmp_path_factory: pytest.TempPathFactory) -> tuple[str, Path]:
    requested = os.environ.get("CODEX_BIN", "codex")
    executable = shutil.which(requested)
    supported = (
        executable is not None
        and subprocess.run(
            [executable, "execpolicy", "check", "--help"], capture_output=True, timeout=10, check=False
        ).returncode
        == 0
    )
    if not supported:
        reason = f"Codex execpolicy check is not available: {requested}"
        if os.environ.get("REQUIRE_CODEX_EXECPOLICY") == "1":
            pytest.fail(reason)
        pytest.skip(reason)
    assert executable is not None
    path = tmp_path_factory.mktemp("codex-policy") / "default.rules"
    agent_harness("generate-codex-rules", "--output", str(path))
    return executable, path


@pytest.mark.parametrize(
    ("decision", "command"),
    [
        ("allow", "uv run --frozen pytest tests/test_main.py"),
        ("allow", "cargo build"),
        ("allow", "cargo metadata --format-version 1"),
        ("allow", "gh pr list"),
        ("allow", "gh pr create -f --base main"),
        ("allow", "git add path/to/file"),
        ("allow", 'git commit -m "feat(test): allow double quotes"'),
        ("allow", "git fetch origin"),
        ("allow", "git push -u origin feat/example"),
        ("allow", "git pull --ff-only"),
        ("allow", "git rebase origin/main"),
        ("allow", "git worktree list"),
        ("allow", "git worktree add -b feat/example ../repo-feat-example origin/main"),
        ("allow", "git worktree remove ../repo-feat-example"),
        ("allow", "git push --force-with-lease --force-if-includes origin feat/example"),
        ("allow", "git rm agents/old.py"),
        ("allow", "git switch -c feat/example"),
        ("allow", "gh stack submit --auto"),
        ("allow", "gh stack view --short"),
        ("allow", "gh pr close 42"),
        ("allow", "rg -n pattern agents"),
        ("allow", "nix flake check"),
        ("allow", "lefthook run pre-commit"),
        ("allow", "uv run --frozen --group audit deptry ."),
        ("allow", "curl -fsS http://localhost:3000/health"),
        ("allow", "bats tests/zsh/cache.bats"),
        ("allow", "bash -n -- ./scripts/git/sign_ssh.sh"),
        ("allow", "uv run --frozen pytest"),
        ("allow", "uv run --frozen ruff check"),
        ("allow", "uv run --frozen ty check"),
        ("allow", "cargo test"),
        ("allow", "cargo check"),
        ("allow", "cargo clippy"),
        ("allow", "cargo fmt --check"),
        ("allow", "go test ./..."),
        ("allow", "go vet ./..."),
        ("allow", "go build ./cmd/app"),
        ("allow", "golangci-lint run"),
        ("allow", "golangci-lint fmt"),
        ("allow", "govulncheck ./..."),
        ("allow", "npm test"),
        ("allow", "npm run lint"),
        ("allow", "npm exec -- vitest run"),
        ("allow", "node --test"),
        ("allow", "pnpm test"),
        ("allow", "pnpm run typecheck"),
        ("allow", "actionlint .github/workflows/ci.yml"),
        ("allow", "autocorrect --lint README.md"),
        ("allow", "commitlint --from HEAD~1 --to HEAD"),
        ("allow", "statix check nix"),
        ("allow", "deadnix nix"),
        ("allow", "nixfmt --check nix/home/default.nix"),
        ("allow", "shellcheck scripts/git/sign_ssh.sh"),
        ("allow", "shfmt -d scripts/git/sign_ssh.sh"),
        ("allow", "dprint check"),
        ("allow", "oxlint src"),
        ("allow", "oxfmt --check src"),
        ("allow", "tsgolint --project tsconfig.json"),
        ("allow", "stylua --check nvim"),
        ("allow", "selene nvim"),
        ("allow", "tex-fmt --check docs/main.tex"),
        ("allow", "uv run python scripts/check_project.py"),
        ("allow", "uv run --frozen python scripts/check_project.py"),
        ("allow", "python3 scripts/check_project.py"),
        ("allow", "sed -i 's/a/b/' README.md"),
        ("allow", "cd src"),
        ("allow", "awk '{print $1}' README.md"),
        ("allow", "cp a.md b.md"),
        ("allow", "nix flake update nixpkgs"),
        ("allow", "rm scratch.txt"),
        ("allow", "uv add requests"),
        ("allow", "uv lock --upgrade-package ruff"),
        ("allow", "cargo add serde"),
        ("allow", "cargo update"),
        ("allow", "pnpm add zod"),
        ("allow", "go get example.com/module@v1.2.3"),
        ("allow", "go mod tidy"),
        ("prompt", "uvx ruff check"),
        ("prompt", "npx cowsay hello"),
        ("prompt", "pnpm dlx cowsay hello"),
        ("prompt", "npm install left-pad"),
        ("prompt", "nix run nixpkgs#hello"),
        ("prompt", "uv run --with httpx python script.py"),
        ("prompt", "gh pr merge 42 --squash"),
        ("prompt", "gh stack merge"),
        ("prompt", "gh release create v1.0.0"),
        ("prompt", "git stash drop"),
        ("prompt", "git remote add upstream https://example.com/repo.git"),
        ("prompt", "kill 1234"),
        ("prompt", "herdr server stop"),
        ("forbidden", "rm -rf /tmp/example"),
        ("forbidden", "brew install ffmpeg"),
        ("forbidden", "uv python install 3.11"),
        ("forbidden", "cargo install ripgrep"),
        ("forbidden", "go install example.com/tool@latest"),
        ("forbidden", "security find-generic-password -s example -w"),
        ("forbidden", "gh repo delete owner/repo"),
        ("forbidden", 'bash -lc "git add path/to/file && rm -rf /tmp/example"'),
    ],
)
def test_generated_policy_decides_without_running_the_command(
    codex_policy: tuple[str, Path], decision: str, command: str
) -> None:
    executable, rules = codex_policy
    result = subprocess.run(
        [executable, "execpolicy", "check", "--rules", str(rules), "--", *shlex.split(command)],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == decision
