"""Find the programs the Stop-time model rules start, only where nothing the agent can write could have put them.

`op` receives the 1Password service-account token, so a lookup through PATH would hand the token to whatever program
stands earlier on it: a project `bin` directory, a `node_modules/.bin`, any directory the agent can write to. Both
programs are therefore taken from fixed system profile directories, and a candidate is used only if its real path is
inside the Nix store (read-only, root-owned) and the file itself is a regular, executable file that belongs to root
and that nobody else can write. Everything else fails closed: the run is skipped and the token is never read.
"""

import getpass
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from model_rules_outcome import Prevented

DEFAULT_STORE_ROOT = Path("/nix/store")
DEFAULT_OWNER_UID = 0
# Tests replace these three to stand a directory in for the store.
STORE_ROOT = DEFAULT_STORE_ROOT
TRUSTED_UID = DEFAULT_OWNER_UID
SYSTEM_PATH = ("/usr/bin", "/bin")
WRITABLE_BY_OTHERS = stat.S_IWGRP | stat.S_IWOTH


def system_directories(user: str) -> tuple[Path, ...]:
    """The directories nix-darwin and Nix publish programs in; all are root-owned, none is in a home or a project."""
    return (
        Path("/etc/profiles/per-user") / user / "bin",
        Path("/run/current-system/sw/bin"),
        Path("/nix/var/nix/profiles/default/bin"),
    )


DIRECTORIES = system_directories(os.environ.get("USER") or getpass.getuser())


@dataclass(frozen=True, slots=True)
class Programs:
    """The two programs of a run, each by the trusted absolute path it was found at."""

    launcher: Path
    reviewer: Path


def locate() -> Programs | Prevented:
    """Both programs, or the reason the run cannot start; the reviewer is checked first."""
    reviewer = resolve("jev-lint")
    if isinstance(reviewer, Prevented):
        return reviewer
    launcher = resolve("op")
    if isinstance(launcher, Prevented):
        return launcher
    return Programs(launcher, reviewer)


def resolve(name: str) -> Path | Prevented:
    """The trusted path of `name`, or why there is none; never a path found through PATH."""
    refusal: Prevented | None = None
    for directory in DIRECTORIES:
        candidate = directory / name
        if not os.path.lexists(candidate):
            continue
        flaw = _flaw(candidate)
        if flaw is None:
            return candidate
        refusal = refusal or Prevented(f"{name} is not trusted ({flaw})")
    return refusal or Prevented(f"{name} is not installed")


def search_path() -> str:
    """The only PATH a child gets: the trusted directories, then the system's own."""
    return os.pathsep.join([*map(str, DIRECTORIES), *SYSTEM_PATH])


def _flaw(candidate: Path) -> str | None:
    """What is wrong with `candidate` as a program to give a secret to, or None when nothing is."""
    try:
        real = candidate.resolve(strict=True)
        metadata = real.stat()
    except OSError, RuntimeError:
        return "it cannot be inspected"
    requirements = (
        ("it is not inside the Nix store", real.is_relative_to(STORE_ROOT)),
        ("it is not a regular file", stat.S_ISREG(metadata.st_mode)),
        ("it is not owned by the trusted owner", metadata.st_uid == TRUSTED_UID),
        ("it is writable by group or others", not metadata.st_mode & WRITABLE_BY_OTHERS),
        ("it is not executable", os.access(real, os.X_OK)),
    )
    return next((flaw for flaw, met in requirements if not met), None)
