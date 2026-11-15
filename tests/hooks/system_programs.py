"""Stand system programs on PATH, as the deployed hooks find them, without depending on the test machine."""

import os
from pathlib import Path

import pytest

SYSTEM_PROGRAM = Path("/bin/echo")


def use_system_programs(directory: Path, monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Put links to a root-owned system program first on PATH under each name."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).symlink_to(SYSTEM_PROGRAM)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")


def use_own_program(directory: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Put a program the session wrote first on PATH, as a project `.venv/bin` could."""
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / name
    program.write_text("#!/bin/sh\nexit 0\n")
    program.chmod(0o755)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
