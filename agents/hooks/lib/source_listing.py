"""List a project's existing source files the way git sees them."""

import os
from pathlib import Path
import subprocess


GIT_TIMEOUT_SECONDS = 10


def remaining_sources(root: Path, extensions: tuple[str, ...], excluded: frozenset[str]) -> list[str]:
    """List existing source files, leaving out those git ignores when the root is a git work tree."""
    try:
        listing = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            capture_output=True,
            check=True,
            timeout=GIT_TIMEOUT_SECONDS,
        ).stdout
    except OSError, subprocess.SubprocessError:
        return walked_sources(root, extensions, excluded)
    names = (os.fsdecode(entry) for entry in listing.split(b"\0"))
    return [name for name in names if name.endswith(extensions) and (root / name).is_file()]


def walked_sources(root: Path, extensions: tuple[str, ...], excluded: frozenset[str]) -> list[str]:
    """List source files by walking the directory, pruning excluded directories, when git cannot answer."""
    found: list[str] = []
    for parent, directories, files in os.walk(root):
        directories[:] = [name for name in directories if name != ".git" and name not in excluded]
        found.extend(str((Path(parent) / name).relative_to(root)) for name in files if name.endswith(extensions))
    return found
