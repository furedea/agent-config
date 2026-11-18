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
import re
import stat
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from model_rule_fixtures import is_model_rule_fixture

# MADR files are `docs/adr/NNNN_words.md`; the index, a template and nested folders are not decisions.
_ADR_PATTERN = "docs/adr/[0-9]*.md"
_FRONT_MATTER_FENCE = "---"
# Reflog subjects of HEAD that mean the session itself created the commit; `commit (merge)` is deliberately absent.
_OWN_REFLOG_SUBJECT = re.compile(
    r"commit(?: \((?:amend|initial|cherry-pick)\))?:|cherry-pick|revert"
    r"|(?:pull\b[^:(]*)?rebase\b[^:]*\((?:pick|reword|edit|squash|fixup|continue)\)"
)


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


def own_committed_paths(root: Path, base: str, registered_entries: int | None) -> tuple[str, ...]:
    """The files the session's own commits since `base` added or changed, with links and replaced types included.

    HEAD's reflog says how each step came to be. A step the session made (commit, amend, cherry-pick, revert, or a
    rebase replaying commits) counts, and so does only what that step changed from the commit HEAD named before it:
    an amend counts what it added, not the commit it replaced. A step that arrived by fast-forward, pull, checkout or
    merge belongs to someone else, so its files are left out even though `base..HEAD` contains them; a merge commit is
    never counted, as its diff cannot be split into the session's part and the part it merged in. Only steps made
    after the session registered (`registered_entries` of them existed then) count. A path counts only if its content
    now differs from `base`, so work that was discarded or undone is not the session's.

    A commit made in another worktree and brought in here by a fast-forward leaves no entry in this reflog and is not
    counted. A rebase replays the commits it finds between its target and HEAD, so after a fast-forward it can turn
    commits that came from elsewhere into the session's. A step's path counts only while HEAD still holds the content
    that step left, which is how a discarded commit stops claiming a path that an outside commit later changed.

    Raises ValueError when the reflog cannot tell: it was not counted at registration, or HEAD moved without an entry;
    `committed_paths` is then the fallback.
    """
    if registered_entries is None:
        raise ValueError("HEAD's reflog was not counted when the session registered")
    steps = [
        tuple(line.partition("\t")[::2])
        for line in _git_lines(root, "reflog", "show", "--format=%H%x09%gs", "HEAD", "--")
    ]
    since_registration = len(steps) - registered_entries
    if since_registration <= 0:
        raise ValueError("HEAD moved but its reflog has no entry since the session registered")
    own = [
        _still_in_head(
            root, commit, _paths_changed_by(root, commit, steps[number + 1][0] if number + 1 < len(steps) else None)
        )
        for number, (commit, subject) in enumerate(steps[:since_registration])
        if _OWN_REFLOG_SUBJECT.match(subject)
    ]
    changed_since_base = set(_paths_changed_between(root, base, "HEAD"))
    return tuple(sorted({path for paths in own for path in paths} & changed_since_base))


def committed_paths(root: Path, base: str) -> tuple[str, ...]:
    """Every file the commits since `base` added or changed, whoever made them, with links and replaced types included.

    The fallback when HEAD's reflog cannot say which commits are the session's: judging too much is better than hiding
    the session's own edits.
    """
    return tuple(sorted(_paths_changed_between(root, base, "HEAD")))


def uncommitted_paths(root: Path) -> frozenset[str]:
    """The files whose working tree content differs from HEAD or the index, or that are untracked and not ignored.

    A file a fast-forward or pull brought in differs from the session's baseline yet matches HEAD, so it is not here.
    """
    output = _git_output(root, "status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all")
    return frozenset(os.fsdecode(entry[3:]) for entry in output.split(b"\0") if entry)


def _still_in_head(root: Path, commit: str, paths: list[str]) -> list[str]:
    """The `paths` HEAD still holds as `commit` left them.

    A step that was discarded, and whose path an outside commit then changed, no longer counts.
    """
    differing = set(_name_only(root, ["diff", commit, "HEAD", "--"], diff_filter=""))
    return [path for path in paths if path not in differing]


def _paths_changed_by(root: Path, commit: str, previous: str | None) -> list[str]:
    if previous is None:
        return _name_only(root, ["diff-tree", "--root", "--no-commit-id", commit])
    return _name_only(root, ["diff", previous, commit, "--"])


def _paths_changed_between(root: Path, base: str, until: str) -> list[str]:
    return _name_only(root, ["diff", base, until, "--"])


def _name_only(root: Path, command: list[str], diff_filter: str = "AMT") -> list[str]:
    """The paths a diff-like `command` names; the options go right after its first word, before any `--`."""
    options = ["-r", "--name-only", "-z", "--no-renames", *([f"--diff-filter={diff_filter}"] if diff_filter else [])]
    output = _git_output(root, command[0], *options, *command[1:])
    return [os.fsdecode(name) for name in output.split(b"\0") if name]


def _git_lines(root: Path, *arguments: str) -> list[str]:
    # Only a newline ends a line: `splitlines` also splits on characters a commit subject may contain.
    return [line for line in _git_output(root, *arguments).decode(errors="replace").split("\n") if line]


def _git_output(root: Path, *arguments: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-c", "core.fsmonitor=false", "-C", str(root), *arguments], stderr=subprocess.DEVNULL
        )
    except OSError, subprocess.CalledProcessError:
        raise ValueError("the commits since the session started cannot be listed") from None


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
