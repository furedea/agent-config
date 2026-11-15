"""Tell whether a program name resolves to a system program, not one the session could have written.

A command the guard lets through by its name runs whatever PATH finds first, and an inherited PATH
may start with a directory the session writes, such as a project `.venv/bin`. A program counts as a
system one only when the directory PATH found it in and the file it resolves to are both owned by
root and writable by nobody else, so a link the session placed to a system file does not count.
Relative names and relative PATH entries depend on a directory the hook cannot see, so they never do,
and under root every file the session writes is root-owned, so nothing counts there.
"""

import os
import pwd
import shutil
import stat
from collections.abc import Callable
from pathlib import Path

ROOT_UID = 0
NIX_STORE = Path("/nix/store")
EXPORTED_FUNCTION_PREFIX = "BASH_FUNC_"
STARTUP_FILE_VARIABLES = ("BASH_ENV", "ENV")
LOADER_PREFIXES = ("LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "DYLD_")
WRITABLE_BY_OTHERS = stat.S_IWGRP | stat.S_IWOTH
# Directories trusted besides root-owned ones; tests stand one in for a system directory.
TRUSTED_DIRECTORIES: frozenset[Path] = frozenset()


def inherits_execution_overrides() -> bool:
    """Whether the shell or the loader may run other code than the program a command names.

    Exported functions arrive as BASH_FUNC_ variables, BASH_ENV or ENV names a file the shell sources
    first, and loader variables such as LD_PRELOAD or DYLD_INSERT_LIBRARIES inject code into every
    dynamically linked program, the shell and the system rm included.
    """
    names = list(os.environ)
    exported = any(name.startswith(EXPORTED_FUNCTION_PREFIX) for name in names)
    loader = any(name.startswith(LOADER_PREFIXES) for name in names)
    return exported or loader or any(os.environ.get(name) for name in STARTUP_FILE_VARIABLES)


def search_path_before(word: str) -> list[Path]:
    """The PATH entries a shell looks in before the one that holds `word`, or all of them if none does."""
    found = shutil.which(word)
    entries = [Path(entry) for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
    if found is None:
        return entries
    parent = Path(found).parent
    return entries[: entries.index(parent)] if parent in entries else entries


def is_system_program(word: str) -> bool:
    """Whether `word`, an absolute path or a name looked up on PATH, runs a root-owned system file."""
    if os.geteuid() == ROOT_UID or inherits_execution_overrides() or ("/" in word and not word.startswith("/")):
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
    """The Nix profile directories, which link into the read-only store and lie outside any session's writes.

    The user's own profile link belongs to the user, whom the session cannot act as outside its sandbox;
    the account comes from the password database, not from variables the environment could set.
    """
    account = pwd.getpwuid(os.getuid())
    home, user = Path(account.pw_dir), account.pw_name
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
    """Whether nobody but root can replace any step of the path, a link included, before the program runs."""
    for step in (directory, *directory.parents):
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
