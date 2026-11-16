"""Disposable verification records, counted check processes, and Herdr fixtures."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.hooks.herdr_runtime import TERMINAL, set_agents
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks"))
sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import cleanup_worktrees
import session_store
from tests.hooks.cleanup_worktrees_runtime import git


@pytest.fixture
def verification_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path.parent / (tmp_path.name + "-state")
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    calls = state / "calls"
    return calls


@pytest.fixture
def verification_record(
    git_project: Path, verification_calls: Path, executable: StubWriter
) -> session_store.SessionRecord:
    (git_project / "pyproject.toml").write_text("")
    (git_project / "source.py").write_text("before")
    (git_project / "tests").mkdir()
    (git_project / "tests/test_source.py").write_text("def test_source(): pass")
    executable(
        "uv",
        f"""
        import os
        from pathlib import Path
        import sys
        with Path({str(verification_calls)!r}).open('a') as stream:
            stream.write(str(Path.cwd()) + '\\n')
        failed = os.environ.get('VERIFICATION_TEST_FAIL') == '1'
        print('1 failed' if failed else '1 passed')
        sys.exit(int(failed))
        """,
    )
    return session_store.register(git_project, "codex", "verification-test")


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    session_store.register(root, "codex", "session")
    return root


@pytest.fixture
def herdr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Live agents and panes come from files the test controls."""
    directory = tmp_path / "bin"
    directory.mkdir()
    names = tmp_path / "live_agents.txt"
    set_agents(names, "")
    script = directory / "herdr"
    workspaces = tmp_path / "workspaces.json"
    workspaces.write_text('{"result":{"workspaces":[]}}')
    worktrees = tmp_path / "worktrees.json"
    worktrees.write_text('{"result":{"worktrees":[]}}')
    panes = tmp_path / "panes.json"
    panes.write_text(json.dumps({"result": {"panes": [{"pane_id": "p1", "terminal_id": TERMINAL}]}}))
    script.symlink_to(Path(__file__).with_name("fake_herdr.sh"))
    monkeypatch.setenv("HERDR_TEST_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
    return names


@pytest.fixture
def primary(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git("init", "--quiet", "--initial-branch=main", cwd=root)
    git("config", "user.email", "test@example.com", cwd=root)
    git("config", "user.name", "Test", cwd=root)
    git("config", "commit.gpgsign", "false", cwd=root)
    (root / "README.md").write_text("base\n")
    git("add", "README.md", cwd=root)
    git("commit", "--quiet", "-m", "base", cwd=root)
    return root


@pytest.fixture(autouse=True)
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep session records out of the developer's real state home."""
    path = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(path))
    return path


@pytest.fixture
def workspace_listing(tmp_path: Path) -> Path:
    """The file the fake Herdr prints for `workspace list`; it starts with no workspaces."""
    path = tmp_path / "herdr_workspaces.json"
    path.write_text('{"result":{"workspaces":[]}}')
    return path


@pytest.fixture
def sandbox_tmp(tmp_path: Path) -> Path:
    """The directory that stands in for the sandbox TMPDIR, which cleanup treats as untrusted."""
    return tmp_path / "sandbox-tmp"


@pytest.fixture
def merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workspace_listing: Path, sandbox_tmp: Path
) -> dict[str, str]:
    """Fake gh and Herdr: merged PR heads come from this dict; Herdr records removals."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text('{"sandbox":{"filesystem":{"allowWrite":[]}}}')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TMPDIR", str(sandbox_tmp))
    monkeypatch.setattr(
        cleanup_worktrees,
        "untrusted_locations",
        lambda: {tmp_path / "writable", sandbox_tmp, Path.home() / cleanup_worktrees.HERDR_WORKTREES},
    )
    directory = tmp_path / "bin"
    directory.mkdir()
    state = tmp_path / "merged.json"
    removed = tmp_path / "herdr_removed.txt"
    (directory / "gh").write_text(f"#!/bin/sh\ncat {state}\n")
    listing = tmp_path / "herdr_worktrees.json"
    listing.write_text('{"result":{"worktrees":[]}}')
    (tmp_path / "herdr_agents.json").write_text('{"result":{"agents":[]}}')
    (tmp_path / "herdr_panes.json").write_text(
        json.dumps({"result": {"panes": [{"pane_id": "p1", "terminal_id": "term_primary"}]}})
    )
    (directory / "herdr").write_text(
        "#!/bin/sh\n"
        f'if [ "$1 $2" = "pane list" ]; then cat {tmp_path / "herdr_panes.json"}; exit 0; fi\n'
        f'if [ "$1 $2" = "workspace list" ]; then cat {workspace_listing}; exit 0; fi\n'
        f'if [ "$1 $2" = "agent list" ]; then cat {tmp_path / "herdr_agents.json"}; exit 0; fi\n'
        f'if [ "$1 $2" = "workspace close" ]; then echo "$@" >> {removed}; exit 0; fi\n'
        f'if [ "$2" = list ]; then cat {listing}; exit 0; fi\n'
        f'echo "$@" >> {removed}\n'
        f'git worktree remove "$(cat {tmp_path / "herdr_path.txt"})"\n'
    )
    for name in ("gh", "herdr"):
        (directory / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")

    class Heads(dict):
        def __setitem__(self, branch: str, oid: str) -> None:
            super().__setitem__(branch, oid)
            state.write_text(json.dumps([{"headRefName": b, "headRefOid": o} for b, o in self.items()]))

    heads = Heads()
    state.write_text("[]")
    return heads


@pytest.fixture
def plain_gh_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """gh resolves its host and repository from these; the guard tests set them only on purpose."""
    for name in ("GH_REPO", "GH_HOST"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def furedea_checkout(isolated_project: Path) -> Path:
    """A repository whose only remote belongs to a trusted owner."""
    subprocess.run(["git", "init", "--quiet"], check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/furedea/agent-config.git"],
        check=True,
        capture_output=True,
    )
    return isolated_project


@pytest.fixture
def scan_samples() -> dict[str, str]:
    """Public synthetic secrets, one per scanned pattern."""
    return json.loads(Path(__file__).with_name("secret_content_samples.json").read_text())


@pytest.fixture
def sent_files(isolated_project: Path) -> Path:
    """The body files the guard tests send, present so the guard can scan them as gh will read them."""
    for name, text in {"notes.txt": "Fixed.\n", "body.json": "{}\n", "body.md": "Fixed.\n", "$=J": "Fixed.\n"}.items():
        (isolated_project / name).write_text(text)
    return isolated_project


@pytest.fixture
def logged_body_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The run-time body files the logged gh forms name, present so the guard can expand and scan them."""
    root = tmp_path / "run"
    for name in ("TMPDIR", "S", "D"):
        monkeypatch.setenv(name, str(root))
    monkeypatch.setenv("f", str(root / "comment"))
    for name in ("body.md", "issue_all_msg.md", "plan74.md", "pr/body.md", "briefs/issue_clippy.md"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("Fixed.\n")
    for name in ("plan242.md", "pr.md", "comment", "comment.new"):
        (root / name).write_text("Fixed.\n")
    return root
