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
NIX_STORE = Path("/nix/store")
EXPORTED_FUNCTION_PREFIX = "BASH_FUNC_"
STARTUP_FILE_VARIABLES = ("BASH_ENV", "ENV")
WRITABLE_BY_OTHERS = stat.S_IWGRP | stat.S_IWOTH
# Directories trusted besides root-owned ones; tests stand one in for a system directory.
TRUSTED_DIRECTORIES: frozenset[Path] = frozenset()


def inherits_shell_functions() -> bool:
    """Whether bash may define functions before the command runs, which shadow builtins and PATH lookups.

    Exported functions arrive as BASH_FUNC_ variables, and BASH_ENV or ENV names a file the shell
    sources first, where any function or alias can be defined.
    """
    exported = any(name.startswith(EXPORTED_FUNCTION_PREFIX) for name in os.environ)
    return exported or any(os.environ.get(name) for name in STARTUP_FILE_VARIABLES)


def is_system_program(word: str) -> bool:
    """Whether `word`, an absolute path or a name looked up on PATH, runs a root-owned system file."""
    if os.geteuid() == ROOT_UID or inherits_shell_functions() or ("/" in word and not word.startswith("/")):
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
    trusted = (
        directory in TRUSTED_DIRECTORIES
        or (Path(found).parent in nix_profiles() and real.is_relative_to(NIX_STORE))
        or (_is_root_owned(directory, stat.S_ISDIR) and _has_fixed_ancestry(Path(found).parent))
    )
    return trusted and _is_root_owned(real, stat.S_ISREG) and os.access(real, os.X_OK)


def nix_profiles() -> frozenset[Path]:
    """The Nix profile directories, which link into the read-only store and lie outside any session's writes."""
    home, user = Path.home(), os.environ.get("USER", "")
    return frozenset(
        {
            home / ".nix-profile" / "bin",
            home / ".local" / "state" / "nix" / "profile" / "bin",
            Path("/etc/profiles/per-user") / user / "bin",
            Path("/run/current-system/sw/bin"),
            Path("/nix/var/nix/profiles/default/bin"),
        }
    )


def _has_fixed_ancestry(directory: Path) -> bool:
    """Whether nobody but root can replace any step of the path, a link included, before the program runs.

    The Nix store is writable only by the Nix daemon and its entries never change, so it ends the walk.
    """
    for step in (directory, *directory.parents):
        if step == NIX_STORE:
            return True
        try:
            metadata = step.lstat()
        except OSError:
            return False
        if metadata.st_uid != ROOT_UID or (
            not stat.S_ISLNK(metadata.st_mode) and metadata.st_mode & WRITABLE_BY_OTHERS
        ):
            return False
    return True


def _is_root_owned(path: Path, is_kind: Callable[[int], bool]) -> bool:
    """Whether the path is of the kind, owned by root, and writable by neither group nor others."""
    try:
        metadata = path.stat()
    except OSError:
        return False
    return is_kind(metadata.st_mode) and metadata.st_uid == ROOT_UID and not metadata.st_mode & WRITABLE_BY_OTHERS
