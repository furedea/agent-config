"""Keep the paths that browser and desktop automation read and write inside the session's own directories."""

import errno
import os
from pathlib import Path

import command_policy
import hook_decision
import hook_input
import session_snapshot
import shell_syntax
from hook_decision import Verdict

# Browser and desktop automation outside the sandbox, whose listed forms must match with quotes removed too.
PROGRAMS = frozenset({"agent-browser", "agent-desktop"})
# agent-browser loads this file from its working directory when present; it can name the browser
# executable, its arguments, the profile, and where screenshots and downloads go.
BROWSER_PROJECT_CONFIG = "agent-browser.json"


def objection(payload: dict, commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask when an automation call may reach a file outside the worktree and the session's temporary directory.

    The programs read and write paths outside the sandbox, so every argument, and every option's value
    after `=`, is resolved from the command's directory through any symlink the session made. A word
    that names no file stays inside, so only words that reach a link pointing elsewhere ask. An
    agent-browser call also asks beside a project config file, which the session may have written.
    """
    calls = [candidate for item in commands if (candidate := command_policy.canonical(item)).arguments[0] in PROGRAMS]
    if not calls:
        return hook_decision.ALLOW
    preview = shell_syntax.command_preview(commands[0].raw)
    directory = working_directory(payload)
    if directory is not None and any(call.arguments[0] == "agent-browser" for call in calls):
        if os.path.lexists(directory / BROWSER_PROJECT_CONFIG):
            return hook_decision.ask(
                f"Needs review: agent-browser loads {BROWSER_PROJECT_CONFIG} from {directory}, and it can "
                f"name the browser executable, its arguments, and where files go.\n\nCommand: {preview}",
                "agent-browser",
            )
    roots = writable_roots(directory) if directory is not None else ()
    word = next((word for candidate in calls if (word := escaping_word(candidate, directory, roots))), "")
    if not word:
        return hook_decision.ALLOW
    return hook_decision.ask(
        f"Needs review: '{word}' may reach a file outside the worktree and the session's temporary "
        f"directory, through a symlink or from an unknown working directory.\n\nCommand: {preview}",
        calls[0].arguments[0],
    )


def escaping_word(candidate: shell_syntax.Command, directory: Path | None, roots: tuple[Path, ...]) -> str:
    """The first word that may reach outside the roots, or an empty string when every word stays inside."""
    words = (word for argument in candidate.arguments[1:] for word in (argument, argument.partition("=")[2]))
    return next((word or "''" for word in words if directory is None or not stays_inside(directory, word, roots)), "")


def working_directory(payload: dict) -> Path | None:
    """The existing absolute directory the provider runs the command in, or None when unknown."""
    value = payload.get("cwd")
    if not isinstance(value, str) or not Path(value).is_absolute():
        return None
    directory = Path(value).resolve()
    return directory if directory.is_dir() else None


def writable_roots(directory: Path) -> tuple[Path, ...]:
    """The worktree holding the command's directory, if any, and the session's temporary directories."""
    try:
        worktree: tuple[Path, ...] = (session_snapshot.repository_root(directory),)
    except session_snapshot.SnapshotError:
        worktree = ()
    return worktree + hook_input.temporary_roots()


def stays_inside(directory: Path, word: str, roots: tuple[Path, ...]) -> bool:
    target = resolved_target(directory, word)
    return target is not None and any(target.is_relative_to(root) for root in roots)


def resolved_target(base: Path, word: str) -> Path | None:
    """The file a word names from `base`, symlinks followed in every existing component.

    None when a component is a dangling or looping symlink or cannot be read, because the file the
    word reaches is then unknown. A name too long to exist stays as written: nothing can open it.
    """
    path = base / word
    if any(prefix.is_symlink() and not prefix.exists() for prefix in (path, *path.parents)):
        return None
    try:
        return Path(os.path.realpath(path, strict=os.path.ALLOW_MISSING))
    except OSError as error:
        return path if error.errno == errno.ENAMETOOLONG else None
