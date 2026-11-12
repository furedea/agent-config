#!/usr/bin/env -S python3 -IB
"""Remove task worktrees and local branches whose pull requests were merged.

A branch goes only when a merged pull request's head is exactly its tip and its worktree is
clean, so a squash merge counts as merged while later or uncommitted work is kept. The primary
checkout, the worktree the caller runs in, and the default branch are never removed; after a
removal the default branch fast-forwards to the merges unless that would disturb work. The sweep
covers the caller's repository and every repository with a Herdr task worktree, so lanes merged
elsewhere go wherever the next session starts.

Usage: cleanup_worktrees.py [--dry-run]
       cleanup_worktrees.py session-start  as a hook, reading the payload's cwd
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import primary_workspaces

PROTECTED_BRANCHES = frozenset({"main", "master"})
MERGED_PULL_REQUEST_LIMIT = "200"
TIMEOUT_SECONDS = 30
REGENERABLE_NAMES = frozenset({".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", ".direnv"})
REGENERABLE_NAMES |= frozenset({"result", "target", ".coverage"})
REGENERABLE_PREFIXES = ("result-",)
HERDR_WORKTREES = Path(".herdr/worktrees")
"""Herdr's default worktrees.directory, holding <repo>/<branch-slug> checkouts."""


@dataclass(frozen=True, slots=True)
class Worktree:
    """A checkout listed by `git worktree list`, with its administrative directory under the primary's .git.

    `admin_dir` is None when no `.git/worktrees/<name>` entry points back at `path`, which marks the checkout
    as unverifiable; such a worktree is never treated as clean.
    """

    path: Path
    branch: str
    admin_dir: Path | None


def main(arguments: list[str]) -> int:
    """Run the CLI or the session-start hook and return the process exit status.

    The hook form never fails the session: any error is swallowed and the status is 0. The CLI form accepts only
    no arguments or `--dry-run`, prints one line per action, and returns 1 on a usage error or a failed sweep.
    """
    if arguments == ["session-start"]:
        try:
            payload = json.load(sys.stdin)
            sweep(Path(payload["cwd"]), dry_run=False)
        except ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError:
            pass
        return 0
    if arguments not in ([], ["--dry-run"]):
        print(__doc__, file=sys.stderr)
        return 1
    try:
        for line in sweep(Path.cwd(), dry_run=bool(arguments)):
            print(line)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"cleanup failed: {error}", file=sys.stderr)
        return 1
    return 0


def sweep(cwd: Path, *, dry_run: bool) -> list[str]:
    """Clean the caller's repository and every repository with a Herdr task worktree."""
    current = toplevel(cwd)
    lanes = sorted(path for path in (Path.home() / HERDR_WORKTREES).glob("*/*") if path.is_dir())
    primaries = {primary for path in [current, *lanes] if path and (primary := _primary_checkout(path))}
    report = []
    for primary in sorted(primaries):
        try:
            report += cleanup(primary, current, dry_run=dry_run)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            report.append(f"skip {primary}: {error}")
    return report


def toplevel(path: Path) -> Path | None:
    """Return the registered worktree root that contains `path`, or None when there is none.

    Only a checkout the trusted primary lists as a linked worktree qualifies, so a nested or forged `.git` is ignored.
    """
    if not path.is_dir():
        return None
    roots = [root for root in (path.resolve(), *path.resolve().parents) if (root / ".git").exists()]
    for root in reversed(roots):
        primary = _primary_checkout(root)
        if primary:
            known = {worktree.path for worktree in linked_worktrees(primary)}
            return next((ancestor for ancestor in roots if ancestor in known), None)
    return None


def _primary_checkout(path: Path) -> Path | None:
    root = (
        next((root for root in (path.resolve(), *path.resolve().parents) if (root / ".git").exists()), None)
        if path.is_dir()
        else None
    )
    if root is None:
        return None
    if _real_primary(root):
        writable = sandbox_writable_paths()
        return root if writable is None or not any(root.is_relative_to(path) for path in writable) else None
    return _lane_primary(root)


def _lane_primary(root: Path) -> Path | None:
    admin = _git_file_target(root)
    if admin is None or admin.parent.name != "worktrees" or admin.parent.parent.name != ".git":
        return None
    primary = admin.parent.parent.parent
    writable = sandbox_writable_paths()
    if not _real_primary(primary) or writable is None or any(primary.is_relative_to(path) for path in writable):
        return None
    try:
        if (
            Path((admin / "gitdir").read_text().strip()).resolve() != root / ".git"
            or (admin / (admin / "commondir").read_text().strip()).resolve() != primary / ".git"
        ):
            return None
        return (
            primary
            if any(worktree.path == root and worktree.admin_dir == admin for worktree in linked_worktrees(primary))
            else None
        )
    except OSError, subprocess.SubprocessError:
        pass
    return None


def _real_primary(path: Path) -> bool:
    return (
        (path / ".git").is_dir()
        and not (path / ".git").is_symlink()
        and not path.is_relative_to((Path.home() / HERDR_WORKTREES).resolve())
    )


def sandbox_writable_paths() -> set[Path] | None:
    """Read rendered home policy before trusting any primary inferred from a lane."""
    home = Path.home().resolve()
    try:
        entries = json.loads((home / ".claude/settings.json").read_text())["sandbox"]["filesystem"]["allowWrite"]
        if not isinstance(entries, list) or any(not isinstance(entry, str) for entry in entries):
            return None
        paths = {
            home / entry.removeprefix("~").lstrip("/") if entry.startswith("~") else home / entry for entry in entries
        }
        paths.update(untrusted_locations())
        return paths | {path.resolve() for path in paths}
    except OSError, ValueError, KeyError, TypeError:
        return None


def untrusted_locations() -> set[Path]:
    """Return locations writable by lanes independently of rendered allowWrite entries."""
    paths = {
        Path("/tmp"),
        Path("/private/tmp"),
        Path("/tmp/claude"),
        Path("/private/tmp/claude"),
        Path.home().resolve() / HERDR_WORKTREES,
    }
    if temporary := os.environ.get("TMPDIR"):
        paths.add(Path(temporary))
    return paths


def cleanup(primary: Path, current: Path | None, *, dry_run: bool) -> list[str]:
    """Remove what is merged in one repository and return one line per removal."""
    merged = merged_heads(primary)
    worktrees = linked_worktrees(primary)
    checked_out = {worktree.branch for worktree in worktrees} | {_current_branch(primary)}
    workspaces = herdr_workspaces(primary)
    report = []
    kept = []
    removed = set()
    for worktree in worktrees:
        if worktree.path in {primary, current} or not _is_merged(primary, worktree.branch, merged):
            continue
        if reason := keep_reason(primary, worktree):
            kept.append(f"keep worktree {worktree.path}: {reason}")
            continue
        removed.add(worktree.path)
        report.append(f"remove worktree {worktree.path} and branch {worktree.branch}")
        if not dry_run:
            remove_worktree(primary, worktree, workspaces.get(worktree.path))
            run("git", "branch", "-D", "--", worktree.branch, cwd=primary)
    for branch in _local_branches(primary) - checked_out:
        if not _is_merged(primary, branch, merged):
            continue
        report.append(f"remove branch {branch}")
        if not dry_run:
            run("git", "branch", "-D", "--", branch, cwd=primary)
    if report:
        report += fast_forward_default_branch(primary, dry_run=dry_run)
    remaining = worktrees if dry_run else linked_worktrees(primary)
    if removed and not any(
        worktree.path != primary and (not dry_run or worktree.path not in removed) for worktree in remaining
    ):
        report += close_primary_workspaces(primary, dry_run=dry_run)
    return report + kept


def keep_reason(primary: Path, worktree: Worktree) -> str | None:
    """Return why a merged branch's worktree must stay, or None when it is safe to remove."""
    if blocker := worktree_blocker(primary, worktree):
        return blocker
    if ignored := irreplaceable_ignored_paths(primary, worktree):
        return f"ignored files would be lost: {', '.join(ignored)}"
    return None


def worktree_blocker(primary: Path, worktree: Worktree) -> str | None:
    """Return why the worktree is not verifiably registered to `primary` and change-free, or None when it is.

    Any mismatch between the worktree's `.git` file, its admin directory, and the primary, any per-worktree
    config, any submodule, or any status entry is a blocker; the check fails closed.
    """
    if reason := _registration_blocker(primary, worktree):
        return reason
    command = ("git", f"--git-dir={worktree.admin_dir}", f"--work-tree={worktree.path}")
    if any(
        entry.startswith("160000 ") for entry in run(*command, "ls-files", "--stage", "-z", cwd=primary).split("\0")
    ):
        return "submodule entry"
    status = run(
        *command,
        "-c",
        "diff.ignoreSubmodules=all",
        "status",
        "--porcelain",
        "--ignore-submodules=all",
        cwd=primary,
    )
    return "uncommitted changes" if status else None


def _registration_blocker(primary: Path, worktree: Worktree) -> str | None:
    admin = worktree.admin_dir
    if not admin:
        return "no admin directory registered for it"
    if _git_file_target(worktree.path) != admin:
        return ".git file does not point at the admin directory"
    try:
        if (admin / (admin / "commondir").read_text().strip()).resolve() != primary / ".git":
            return "commondir does not point at the primary"
        if Path((admin / "gitdir").read_text().strip()).resolve() != worktree.path / ".git":
            return "gitdir does not point back at the worktree"
    except OSError:
        return "admin directory cannot be read"
    return "config.worktree is present" if (admin / "config.worktree").exists() else None


def irreplaceable_ignored_paths(primary: Path, worktree: Worktree) -> list[str]:
    """List ignored paths that are not regenerable caches, which a forced removal would delete."""
    command = ("git", f"--git-dir={worktree.admin_dir}", f"--work-tree={worktree.path}")
    output = run(
        *command,
        "status",
        "--porcelain",
        "--ignored=matching",
        "--untracked-files=normal",
        "--ignore-submodules=all",
        "-z",
        cwd=primary,
    )
    paths = [entry.removeprefix("!! ") for entry in output.split("\0") if entry.startswith("!! ")]
    claude = worktree.path / ".claude"
    return [p for p in paths if not is_regenerable(primary, command, p) and not is_session_scratch(claude, p)]


def is_session_scratch(claude: Path, path: str) -> bool:
    """Claude Code's .cc-writes is disposable, alone or as the only content of an ignored .claude/."""
    if claude.is_symlink() or not claude.is_dir() or Path(path).parts[:1] != (".claude",):
        return False
    return Path(path).parts[1:2] == (".cc-writes",) or {entry.name for entry in claude.iterdir()} <= {".cc-writes"}


def is_regenerable(primary: Path, command: tuple[str, ...], path: str) -> bool:
    """A cache name counts only for an ancestor that holds no tracked file."""
    parts = Path(path).parts
    return any(
        (part in REGENERABLE_NAMES or part.startswith(REGENERABLE_PREFIXES))
        and not run(*command, "ls-files", "--", "/".join(parts[: index + 1]), cwd=primary)
        for index, part in enumerate(parts)
    )


def close_primary_workspaces(primary: Path, *, dry_run: bool) -> list[str]:
    """Close an agent-created primary only while its identity matches and no agent occupies it."""
    try:
        identities = primary_workspaces.idle_primary_workspaces(primary)
    except OSError, subprocess.SubprocessError, ValueError, TypeError:
        return []
    if dry_run:
        return [f"close primary workspace {identity} ({primary})" for identity in identities]
    report = []
    for identity in identities:
        try:
            run("herdr", "workspace", "close", identity, cwd=primary)
        except subprocess.CalledProcessError as error:
            report.append(f"failed to close primary workspace {identity} ({primary}): {error}")
            continue
        report.append(f"close primary workspace {identity} ({primary})")
    return report


def fast_forward_default_branch(primary: Path, *, dry_run: bool) -> list[str]:
    """Bring the default branch up to the merges just cleaned up, without touching other work.

    A checked-out default branch is pulled only when its tree is clean; otherwise only its ref
    moves, through a fetch that refuses anything but a fast-forward.
    """
    branch = next((name for name in sorted(PROTECTED_BRANCHES) if _has_branch(primary, name)), "")
    if not branch:
        return []
    checked_out = _current_branch(primary) == branch
    if checked_out and run("git", "status", "--porcelain", cwd=primary):
        return []
    pull = ("git", "pull", "--quiet", "--ff-only")
    fetch = ("git", "fetch", "--quiet", "--", "origin", f"{branch}:{branch}")
    if not dry_run:
        try:
            run(*(pull if checked_out else fetch), cwd=primary)
        except subprocess.CalledProcessError:
            return []
    return [f"fast-forward {branch}"]


def _has_branch(primary: Path, branch: str) -> bool:
    return bool(run("git", "for-each-ref", "--format=%(refname)", f"refs/heads/{branch}", cwd=primary))


def _is_merged(primary: Path, branch: str, merged: dict[str, set[str]]) -> bool:
    if not branch or branch in PROTECTED_BRANCHES:
        return False
    return run("git", "rev-parse", "--verify", "--end-of-options", f"refs/heads/{branch}", cwd=primary) in merged.get(
        branch, set()
    )


def merged_heads(primary: Path) -> dict[str, set[str]]:
    """Map each branch to the head commits of its merged pull requests."""
    output = run(
        "gh",
        "pr",
        "list",
        "--state",
        "merged",
        "--limit",
        MERGED_PULL_REQUEST_LIMIT,
        "--json",
        "headRefName,headRefOid",
        cwd=primary,
    )
    heads: dict[str, set[str]] = {}
    for pull_request in json.loads(output or "[]"):
        heads.setdefault(pull_request["headRefName"], set()).add(pull_request["headRefOid"])
    return heads


def linked_worktrees(primary: Path) -> list[Worktree]:
    """List every worktree of `primary`, the primary checkout included, with resolved paths.

    Raises OSError or subprocess.SubprocessError when git or the admin directories cannot be read.
    """
    admin_dirs = {
        Path((admin / "gitdir").read_text().strip()).parent.resolve(): admin.resolve()
        for admin in (primary / ".git/worktrees").glob("*")
        if (admin / "gitdir").is_file()
    }
    worktrees = []
    for block in run("git", "worktree", "list", "--porcelain", cwd=primary).split("\n\n"):
        fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        branch = fields.get("branch", "").removeprefix("refs/heads/")
        if "worktree" in fields:
            path = Path(fields["worktree"]).resolve()
            worktrees.append(Worktree(path, branch, admin_dirs.get(path)))
    return worktrees


def _git_file_target(path: Path) -> Path | None:
    try:
        if (path / ".git").is_symlink():
            return None
        content = (path / ".git").read_text().strip()
        if content.startswith("gitdir: "):
            return (path / content.removeprefix("gitdir: ")).resolve()
    except OSError:
        pass
    return None


def _local_branches(primary: Path) -> set[str]:
    return set(run("git", "for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=primary).splitlines())


def _current_branch(primary: Path) -> str:
    return run("git", "branch", "--show-current", cwd=primary)


def herdr_workspaces(primary: Path) -> dict[Path, str]:
    """Map open Herdr worktree workspaces by path; without Herdr there are none to close."""
    try:
        output = run("herdr", "worktree", "list", "--cwd", str(primary), cwd=primary)
        worktrees = json.loads(output)["result"]["worktrees"]
    except OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError:
        return {}
    return {
        Path(item["path"]).resolve(): item["open_workspace_id"]
        for item in worktrees
        if isinstance(item, dict) and item.get("path") and item.get("open_workspace_id")
    }


def remove_worktree(primary: Path, worktree: Worktree, workspace: str | None) -> None:
    """Remove a checkout already verified clean, closing its Herdr workspace when one is open."""
    run("git", "worktree", "remove", "--force", "--", str(worktree.path), cwd=primary)
    if workspace:
        run("herdr", "workspace", "close", workspace, cwd=primary)


def run(*command: str, cwd: Path) -> str:
    """Run a command in `cwd` with a scrubbed environment and return its stripped stdout.

    A `git` command is pinned to `cwd`'s repository and runs with hooks, fsmonitor, LFS filters, system config and
    inherited GIT_* variables disabled, so repository-controlled configuration cannot execute code. A non-zero exit
    raises subprocess.CalledProcessError and a run past TIMEOUT_SECONDS raises subprocess.TimeoutExpired.
    """
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    if command[0] == "git":
        environment.update(GIT_COMMON_DIR=str(cwd / ".git"), GIT_CONFIG_NOSYSTEM="1")
        location = (
            ()
            if command[1].startswith("--git-dir=")
            else (
                f"--git-dir={cwd / '.git'}",
                f"--work-tree={cwd}",
            )
        )
        command = (
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "extensions.worktreeConfig=false",
            *(
                ("-c", "filter.lfs.process=", "-c", "filter.lfs.clean=", "-c", "filter.lfs.smudge=")
                if not location
                else ()
            ),
            *location,
            *command[1:],
        )
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=TIMEOUT_SECONDS,
        env=environment,
    ).stdout.strip()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
