"""Tell whether a program name resolves to a system program, not one the session could have written.

A command the guard lets through by its name runs whatever PATH finds first, and an inherited PATH
may start with a directory the session writes, such as a project `.venv/bin`. A file there belongs to
the user, so a program counts as a system one only when its real path is a regular executable file
owned by root that group and others cannot write.
"""

import os
import shutil
import stat
from pathlib import Path

ROOT_UID = 0
WRITABLE_BY_OTHERS = stat.S_IWGRP | stat.S_IWOTH


def is_system_program(word: str) -> bool:
    """Whether `word`, a path or a name looked up on PATH, runs a root-owned file nobody else can write."""
    found = word if "/" in word else shutil.which(word)
    if found is None:
        return False
    try:
        real = Path(found).resolve(strict=True)
        metadata = real.stat()
    except OSError, RuntimeError:
        return False
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == ROOT_UID
        and not metadata.st_mode & WRITABLE_BY_OTHERS
        and os.access(real, os.X_OK)
    )
