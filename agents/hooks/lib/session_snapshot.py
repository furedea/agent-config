"""Capture verification inputs without storing source content or a Git index."""

from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


# Larger tracked files are signed by metadata so SessionStart stays inside its hook timeout.
HASH_LIMIT_BYTES = 1 << 20


class SnapshotError(ValueError):
    """The worktree cannot provide a complete, stable verification snapshot."""


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Sorted path signatures for tracked and nonignored untracked files."""

    entries: tuple[tuple[str, str], ...]

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.entries, ensure_ascii=True).encode()).hexdigest()

    def changed_paths(self, current: Snapshot) -> tuple[str, ...]:
        before, after = dict(self.entries), dict(current.entries)
        return tuple(sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path)))

    def to_json(self) -> dict[str, str]:
        return dict(self.entries)

    @classmethod
    def from_json(cls, value: object) -> Snapshot:
        if not isinstance(value, dict) or not all(
            isinstance(path, str)
            and path
            and not Path(path).is_absolute()
            and ".." not in Path(path).parts
            and isinstance(signature, str)
            and signature
            for path, signature in value.items()
        ):
            raise SnapshotError("Invalid baseline file signatures")
        return cls(tuple(sorted(value.items())))


def repository_root(directory: Path) -> Path:
    """Resolve the actual worktree, independently of remote refs and shell state."""
    try:
        result = subprocess.check_output(
            ["git", "-c", "core.fsmonitor=false", "-C", str(directory), "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        )
        return Path(os.fsdecode(result).rstrip("\n")).resolve()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SnapshotError(f"No Git worktree at {directory}") from error


def capture(root: Path, *, hash_content: bool = True) -> Snapshot:
    """Sign tracked and nonignored untracked files; a bad individual input never fails the snapshot."""
    root = root.resolve()
    try:
        output = subprocess.check_output(
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-t",
                "-z",
            ],
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise SnapshotError(f"Cannot snapshot {root}: {error}") from error
    tracked: dict[str, bool] = {}
    for record in filter(None, output.split(b"\0")):
        tag, _, name = os.fsdecode(record).partition(" ")
        # Untracked content is neither hashed nor trusted: it is the unbounded, agent-generated part.
        tracked[name] = tracked.get(name, True) and tag != "?"
    entries = []
    for name in sorted(tracked):
        signature = file_signature(root, root / name, hash_content=hash_content and tracked[name])
        if signature is not None:
            entries.append((name, signature))
    return Snapshot(tuple(entries))


def file_signature(root: Path, path: Path, *, hash_content: bool = True) -> str | None:
    """Sign one input without following links out of the worktree; None means it no longer exists."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        return f"unavailable:{errno.errorcode.get(error.errno or 0, 'EIO')}"
    if stat.S_ISLNK(metadata.st_mode):
        return link_signature(root, path, hash_content=hash_content)
    if stat.S_ISDIR(metadata.st_mode):
        # Only a nested repository reaches here: Git lists files, not directories.
        return f"submodule:{capture(path, hash_content=hash_content).digest}"
    if stat.S_ISREG(metadata.st_mode) and hash_content and metadata.st_size <= HASH_LIMIT_BYTES:
        return content_signature(path, metadata)
    return stat_signature(metadata)


def link_signature(root: Path, path: Path, *, hash_content: bool) -> str:
    """Record link text, and the target's signature only for a regular file inside the worktree."""
    text = f"link:{os.readlink(path)}"
    try:
        resolved = path.resolve(strict=True)
        inside = resolved.is_relative_to(root) and resolved.is_file()
    except OSError, RuntimeError:
        return text
    if not inside:
        return text
    target = file_signature(root, resolved, hash_content=hash_content)
    return text if target is None else f"{text}:{target}"


def content_signature(path: Path, metadata: os.stat_result) -> str:
    """Hash content, falling back to metadata when the file cannot be read; reject a file that moves mid-read."""
    try:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = path.stat()
    except OSError:
        return stat_signature(metadata)
    if (metadata.st_ino, metadata.st_size, metadata.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise SnapshotError(f"Input changed while being read: {path}")
    return f"file:{bool(metadata.st_mode & 0o111)}:{digest}"


def stat_signature(metadata: os.stat_result) -> str:
    """ctime cannot be set by a user, so restoring size and mtime after an edit is still detected."""
    mode = stat.S_IMODE(metadata.st_mode)
    return f"stat:{stat.S_IFMT(metadata.st_mode):o}:{mode:o}:{metadata.st_size}:{metadata.st_mtime_ns}:{metadata.st_ctime_ns}"
