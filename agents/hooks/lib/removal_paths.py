"""Let rm run unprompted only on files inside the worktree and the session's temporary directories.

Provider prefix rules see words, not paths, so this guard resolves each operand instead. Git cannot
restore what rm deletes, so Git metadata, paths outside those roots, operands known only at run
time, and recursive removal ask.
"""

from pathlib import Path

import automation_paths
import command_policy
import hook_decision
import shell_syntax
from hook_decision import Verdict

PROGRAM = "rm"
RECURSIVE_SHORT = frozenset("rR")
RECURSIVE_LONG = "--recursive"
GIT_DIRECTORY = ".git"


def objection(payload: dict, commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask when any rm call may delete something outside the session's writable roots or Git's own files."""
    calls = [candidate for item in commands if (candidate := command_policy.canonical(item)).arguments[0] == PROGRAM]
    if not calls:
        return hook_decision.ALLOW
    directory = automation_paths.working_directory(payload)
    roots = automation_paths.writable_roots(directory) if directory is not None else ()
    reason = next((reason for call in calls if (reason := _call_reason(call, directory, roots))), "")
    if not reason:
        return hook_decision.ALLOW
    preview = shell_syntax.command_preview(calls[0].raw)
    return hook_decision.ask(f"Needs review: rm {reason}.\n\nCommand: {preview}", PROGRAM)


def _call_reason(call: shell_syntax.Command, directory: Path | None, roots: tuple[Path, ...]) -> str:
    if call.appends_input:
        return "takes more operands from xargs, which are known only at run time"
    options, operands = _split(call)
    if any(_is_recursive(option) for option in options):
        return "removes directory trees, which Git cannot restore"
    if directory is None:
        return "runs from an unknown working directory"
    return next((reason for operand in operands if (reason := _operand_reason(operand, directory, roots))), "")


def _split(call: shell_syntax.Command) -> tuple[list[str], list[tuple[str, bool]]]:
    """Options and (operand, known only at run time) pairs; every word after `--` is an operand."""
    options: list[str] = []
    operands: list[tuple[str, bool]] = []
    ended = False
    for word, dynamic in zip(call.arguments[1:], call.dynamic[1:], strict=True):
        if not ended and word == "--":
            ended = True
        elif not ended and not dynamic and word.startswith("-") and word != "-":
            options.append(word)
        else:
            operands.append((word, dynamic))
    return options, operands


def _is_recursive(option: str) -> bool:
    if option.startswith("--"):
        return len(option) > len("--") and RECURSIVE_LONG.startswith(option)
    return bool(RECURSIVE_SHORT & set(option[1:]))


def _operand_reason(operand: tuple[str, bool], directory: Path, roots: tuple[Path, ...]) -> str:
    word, dynamic = operand
    if dynamic:
        return f"names '{word}', which is known only at run time"
    target = _removed_entry(directory, word)
    if target is None:
        return f"names '{word}' through a link that cannot be resolved"
    if _names_git_metadata(Path(word)) or _names_git_metadata(target):
        return f"deletes Git metadata at '{word}'"
    if not any(target.is_relative_to(root) for root in roots):
        return f"deletes '{word}' outside the worktree and the session's temporary directories"
    return ""


def _removed_entry(directory: Path, word: str) -> Path | None:
    """The entry rm unlinks: its parent resolved through links, its own name kept, as rm removes a link itself."""
    path = Path(word).expanduser()
    if path.name in {"", ".", ".."}:
        return automation_paths.resolved_target(directory, word)
    parent = automation_paths.resolved_target(directory, str(path.parent))
    return parent / path.name if parent is not None else None


def _names_git_metadata(path: Path) -> bool:
    return any(part.casefold() == GIT_DIRECTORY for part in path.parts)
