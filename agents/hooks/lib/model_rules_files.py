"""Choose which of a session's changed files may be sent to the model, and withhold the rest.

What leaves the machine is the content of the files named to `jev-lint`, and `jev-lint` reads a path the way any
program does: through symbolic links. A link committed or created inside the repository could therefore make it read
`~/.ssh/config`. Only regular files whose real path is inside the repository are sent; a link, or a file reached
through a directory that now links elsewhere, is withheld. Withheld paths are kept apart from the sendable ones and
only their number is reported, because their names may themselves be sensitive.
"""

import os
import stat
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Selection:
    """The files of one review that may be sent, and the changed files that were withheld instead."""

    sendable: tuple[str, ...] = ()
    withheld: frozenset[str] = frozenset()


def select(root: Path, paths: Iterable[str]) -> Selection:
    """Split changed `paths` of the repository at `root` into the sendable and the withheld.

    A path that no longer exists, is not a file (a nested repository), or reads like an option has nothing to send and
    is left out without being counted.
    """
    real_root = root.resolve()
    sendable: list[str] = []
    withheld: set[str] = set()
    for path in paths:
        verdict = _verdict(real_root, root / path, path)
        if verdict is True:
            sendable.append(path)
        elif verdict is False:
            withheld.add(path)
    return Selection(tuple(sendable), frozenset(withheld))


def committed_paths(root: Path, base: str) -> tuple[str, ...]:
    """The files the commits since `base` added or changed, with links and replaced types included."""
    try:
        output = subprocess.check_output(
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(root),
                "diff",
                "--name-only",
                "-z",
                "--no-renames",
                "--diff-filter=AMT",
                base,
                "HEAD",
                "--",
            ],
            stderr=subprocess.DEVNULL,
        )
    except OSError, subprocess.CalledProcessError:
        raise ValueError("the commits since the session started cannot be listed") from None
    return tuple(sorted(os.fsdecode(name) for name in output.split(b"\0") if name))


def _verdict(real_root: Path, candidate: Path, path: str) -> bool | None:
    """True to send, False to withhold, None when there is nothing to send."""
    if path.startswith("-"):
        return None
    try:
        mode = candidate.lstat().st_mode
    except OSError:
        return None
    if stat.S_ISLNK(mode):
        return False
    if not stat.S_ISREG(mode):
        return None
    try:
        return candidate.resolve(strict=True).is_relative_to(real_root)
    except OSError, RuntimeError:
        return False
