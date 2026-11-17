"""Choose which of a session's changed files may be sent to the model, and withhold the rest.

What leaves the machine is the content of the files named to `jev-lint`, and `jev-lint` reads a path the way any
program does: through symbolic links. A link committed or created inside the repository could therefore make it read
`~/.ssh/config`. Only regular files whose real path is inside the repository and that have no other hard link are
sent; a symbolic link, a file reached through a directory that now links elsewhere, and a hard-linked file (whose
other name may be outside the repository) are withheld. Withheld paths are kept apart from the sendable ones and only
their number is reported, because their names may themselves be sensitive.

The check happens when the files are chosen, a moment before the child opens them. The agent is not running while the
Stop hook runs, so only a process it left behind could race that gap; closing it would need a private copy of the
files, which is not done here.
"""

import os
import stat
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from model_rule_fixtures import is_model_rule_fixture

# MADR files are `docs/adr/NNNN_words.md`; the index, a template and nested folders are not decisions.
_ADR_PATTERN = "docs/adr/[0-9]*.md"
_FRONT_MATTER_FENCE = "---"


@dataclass(frozen=True, slots=True)
class Selection:
    """The files of one review that may be sent, and the changed files that were withheld instead.

    `adrs` are the sendable ADRs that are new or whose body (after the front matter) changed: the only files the ADR
    rules may judge.
    """

    sendable: tuple[str, ...] = ()
    withheld: frozenset[str] = frozenset()
    adrs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewedSpan:
    """The change one review judges: from the revision `since` to the revision `until`, or to the working tree."""

    since: str
    until: str | None = None


def select(root: Path, paths: Iterable[str], span: ReviewedSpan) -> Selection:
    """Split changed `paths` of the repository at `root` into the sendable and the withheld.

    A path that no longer exists, is not a file (a nested repository), reads like an option, or is a rule fixture has
    nothing to send and is left out without being counted. An ADR's body is compared across `span`, the change the
    review judges.
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
    adrs = tuple(path for path in sendable if _is_changed_adr(root, path, span))
    return Selection(tuple(sendable), frozenset(withheld), adrs)


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
    if path.startswith("-") or is_model_rule_fixture(path):
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
        # A second name for a file that may live outside the repository looks like any other regular file.
        return candidate.stat().st_nlink == 1 and candidate.resolve(strict=True).is_relative_to(real_root)
    except OSError, RuntimeError:
        return False


def _is_changed_adr(root: Path, path: str, span: ReviewedSpan) -> bool:
    """Whether `path` is an ADR that is new at `span.since` or whose body differs from the one there."""
    if not PurePosixPath(path).full_match(_ADR_PATTERN):
        return False
    current = _text_in_tree(root, path) if span.until is None else _text_at(root, span.until, path)
    if current is None:
        return False
    earlier = _text_at(root, span.since, path)
    return earlier is None or _body(earlier) != _body(current)


def _text_in_tree(root: Path, path: str) -> str | None:
    try:
        return (root / path).read_text()
    except OSError, UnicodeDecodeError:
        return None


def _text_at(root: Path, revision: str, path: str) -> str | None:
    """The file at `revision`, or None when it did not exist there or cannot be read."""
    try:
        output = subprocess.check_output(
            ["git", "-c", "core.fsmonitor=false", "-C", str(root), "show", f"{revision}:{path}"],
            stderr=subprocess.DEVNULL,
        )
        return output.decode()
    except OSError, subprocess.CalledProcessError, UnicodeDecodeError:
        return None


def _body(text: str) -> str:
    """The text after a leading YAML front matter; a document without one is all body."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != _FRONT_MATTER_FENCE:
        return text
    for number, line in enumerate(lines[1:], start=1):
        if line.rstrip() == _FRONT_MATTER_FENCE:
            return "".join(lines[number + 1 :])
    return text
