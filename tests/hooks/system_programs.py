"""Stand system programs on PATH, as the deployed hooks find them, without depending on the test machine."""

import os
import sys
from pathlib import Path

import pytest
from tests.runtime import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import system_programs

SYSTEM_PROGRAM = Path("/bin/echo")


def use_system_programs(directory: Path, monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Put links to a root-owned system program first on PATH under each name.

    The directory belongs to the test user, so the links count as system programs only once the
    directory is trusted with `trust_directory`.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).symlink_to(SYSTEM_PROGRAM)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")


def trust_directory(directory: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the guard treat a test directory as a root-owned system directory."""
    trusted = system_programs.TRUSTED_DIRECTORIES | {directory.resolve()}
    monkeypatch.setattr(system_programs, "TRUSTED_DIRECTORIES", trusted)


def use_own_program(directory: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Put a program the session wrote first on PATH, as a project `.venv/bin` could."""
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / name
    program.write_text("#!/bin/sh\nexit 0\n")
    program.chmod(0o755)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
