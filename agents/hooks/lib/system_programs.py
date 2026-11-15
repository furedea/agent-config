"""Tell whether a program name resolves to a system program, not one the session could have written.

A command the guard lets through by its name runs whatever PATH finds first, and an inherited PATH
may start with a directory the session writes, such as a project `.venv/bin`. A program counts as a
system one only when the directory PATH found it in and the file it resolves to are both owned by
root and writable by nobody else, so a link the session placed to a system file does not count.
Relative names and relative PATH entries depend on a directory the hook cannot see, so they never do,
and under root every file the session writes is root-owned, so nothing counts there.
"""

import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path

ROOT_UID = 0
WRITABLE_BY_OTHERS = stat.S_IWGRP | stat.S_IWOTH
# Directories trusted besides root-owned ones; tests stand one in for a system directory.
TRUSTED_DIRECTORIES: frozenset[Path] = frozenset()


def is_system_program(word: str) -> bool:
    """Whether `word`, an absolute path or a name looked up on PATH, runs a root-owned system file."""
    if os.geteuid() == ROOT_UID or ("/" in word and not word.startswith("/")):
        return False
    entries = os.environ.get("PATH", "").split(os.pathsep)
    if "/" not in word and not all(Path(entry).is_absolute() for entry in entries):
        return False
    found = word if "/" in word else shutil.which(word)
    if found is None:
        return False
    try:
        directory = Path(found).parent.resolve(strict=True)
        real = Path(found).resolve(strict=True)
    except OSError, RuntimeError:
        return False
    trusted = directory in TRUSTED_DIRECTORIES or _is_root_owned(directory, stat.S_ISDIR)
    return trusted and _is_root_owned(real, stat.S_ISREG) and os.access(real, os.X_OK)


def _is_root_owned(path: Path, is_kind: Callable[[int], bool]) -> bool:
    """Whether the path is of the kind, owned by root, and writable by neither group nor others."""
    try:
        metadata = path.stat()
    except OSError:
        return False
    return is_kind(metadata.st_mode) and metadata.st_uid == ROOT_UID and not metadata.st_mode & WRITABLE_BY_OTHERS
