"""Setup and helpers shared by the Stop-time model rules tests.

Each test module wraps `install_fakes` and `register_session` in its own fixtures, so the fake programs and the session
in a trusted repository are the same in every file.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import Tools, install_tools
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import model_rules_programs
import model_rules_run
import session_gate
import session_store


def install_fakes(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tools:
    """Put the fake programs in place for one test: no Keychain, no 1Password, no model, no network."""
    monkeypatch.setenv("USER", "tester")
    monkeypatch.delenv("AGENT_MODEL_RULES", raising=False)
    # Outside the worktree: the fakes' call log changes on every run and must not count as an edit.
    fakes = install_tools(executable, tmp_path.parent / f"{tmp_path.name}-fakes")
    # The hook names `timeout` by absolute path, so the fake has to stand at the path it uses.
    monkeypatch.setattr(model_rules_run, "TIMEOUT_PROGRAM", str(fakes.timeout))
    # The programs are looked up only in trusted places, so the fake directory stands in for the Nix store: it is the
    # one trusted directory, its real path is the store root, and the test user is the trusted owner.
    programs = tmp_path / "bin"
    monkeypatch.setattr(model_rules_programs, "DIRECTORIES", (programs,))
    monkeypatch.setattr(model_rules_programs, "STORE_ROOT", programs.resolve())
    monkeypatch.setattr(model_rules_programs, "TRUSTED_UID", os.getuid())
    return fakes


def register_session(
    git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> session_store.SessionRecord:
    """A session registered in a repository of a trusted owner, before any edit."""
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/furedea/fixture.git"], cwd=git_project, check=True
    )
    trusted = tmp_path / "trusted_owners.json"
    trusted.write_text(json.dumps({"owners": ["furedea"], "exclude_forks": True, "repositories": ["furedea/fixture"]}))
    monkeypatch.setenv("AGENT_TRUSTED_OWNERS", str(trusted))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path.parent / f"{tmp_path.name}-state"))
    (git_project / "notes.txt").write_text("before\n")
    (git_project / "preexisting.txt").write_text("already here when the session starts\n")
    return session_store.register(git_project, "claude", "model-rules")


def edit(record: session_store.SessionRecord, text: str) -> None:
    (record.root / "notes.txt").write_text(text)


def commit_file(record: session_store.SessionRecord, name: str) -> None:
    (record.root / name).write_text("committed\n")
    subprocess.run(["git", "add", name], cwd=record.root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "later"], cwd=record.root, check=True)


def stop(record: session_store.SessionRecord, *, active: bool = False) -> dict:
    return session_gate.stop(record, stop_hook_active=active)
