"""Let rm run unprompted only on files inside the worktree and the session's temporary directories.

Provider prefix rules see words, not paths, so this guard resolves each operand instead. Git cannot
restore what rm deletes, so Git metadata, paths outside those roots, operands known only at run
time, and recursive removal ask, and so does rm beside any program that is not a listed
read-only one, since it may move the working directory or create a link before rm runs.
"""

import os
import re
from pathlib import Path

import automation_paths
import command_policy
import hook_decision
import literal_words
import session_snapshot
import shell_inspection
import shell_syntax
import system_programs
from hook_decision import Verdict

PROGRAM = "rm"
RECURSIVE_SHORT = frozenset("rR")
RECURSIVE_LONG = "--recursive"
GIT_DIRECTORY = ".git"
# Programs that may share a command with rm: they neither move the working directory nor create
# files, so rm's operands still name what they named when the guard resolved them. A wrapper here
# runs its rm, which the guard judges as its own call. Each is a shell builtin named bare without an
# assignment before it, so neither a path nor an inherited PATH can swap in another program.
COMPANIONS = frozenset({"echo", "true", "false", "test", "[", "pwd"})
WRAPPERS = frozenset({"command", "nohup", "nice", "time", "timeout", "stdbuf"})
# Companions the shell runs itself; every other program, rm included, is found through PATH.
BUILTINS = COMPANIONS | {"command"}
# System temporary roots other programs and users share; only a session's own directory below one counts.
SHARED_TEMPORARY_ROOTS = frozenset(
    Path(path).resolve() for path in ("/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp", "/dev/shm")
)
# Variables naming the parent a provider creates its session directories in; only its claude-* children
# count, and a general TMPDIR counts only as such a directory directly below a shared root.
PROVIDER_TEMPORARY_VARIABLES = ("CLAUDE_TMPDIR", "CLAUDE_CODE_TMPDIR")
PROVIDER_TEMPORARY_PREFIX = "claude-"
# macOS's per-user temporary directory, which every program the user runs shares.
PER_USER_TEMPORARY_ROOT = re.compile(r"/(private/)?var/folders/[^/]+/[^/]+/T")


def objection(payload: dict, command: str, commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask when any rm call may delete something outside the session's writable roots or Git's own files."""
    calls = [candidate for item in commands if (candidate := command_policy.canonical(item)).arguments[0] == PROGRAM]
    if not calls:
        return hook_decision.ALLOW
    preview = shell_syntax.command_preview(calls[0].raw)
    if other := next((item.arguments[0] for item in commands if not _is_safe_companion(item)), ""):
        return hook_decision.ask(
            f"Needs review: rm shares the command with '{other}', which may change the working directory or the "
            f"file a path names, so its operands cannot be resolved beforehand.\n\nCommand: {preview}",
            PROGRAM,
        )
    if shell_inspection.changes_variables(command) or not literal_words.has_literal_words(command):
        return hook_decision.ask(
            f"Needs review: rm runs beside a variable change or an expansion, which can change PATH and so the "
            f"program it runs."
            f"\n\nCommand: {preview}",
            PROGRAM,
        )
    programs = [item.arguments[0] for item in commands if not _runs_a_system_program(item)]
    if program := next(iter(programs), ""):
        return hook_decision.ask(
            f"Needs review: '{program}' does not resolve to a system program, so it may not be the program the "
            f"guard judged.\n\nCommand: {preview}",
            PROGRAM,
        )
    directory = automation_paths.working_directory(payload)
    roots = _writable_roots(directory) if directory is not None else ()
    reason = next((reason for call in calls if (reason := _call_reason(call, directory, roots))), "")
    if not reason:
        return hook_decision.ALLOW
    return hook_decision.ask(f"Needs review: rm {reason}.\n\nCommand: {preview}", PROGRAM)


def _writable_roots(directory: Path) -> tuple[Path, ...]:
    """The worktree holding the directory, if any, and the session's own temporary directories."""
    root = worktree_root(directory)
    return (() if root is None else (root,)) + _session_temporary_roots()


def worktree_root(directory: Path) -> Path | None:
    """The narrower of git's worktree and the nearest directory holding a valid `.git`, or None if they disagree.

    Git's answer follows settings such as core.worktree, and a `.git` can be planted, so neither alone
    is trusted: each can only narrow what the other reports.
    """
    on_disk = next((folder for folder in (directory, *directory.parents) if _is_git_entry(folder / ".git")), None)
    try:
        reported = session_snapshot.repository_root(directory).resolve()
    except session_snapshot.SnapshotError:
        return None
    if on_disk is None:
        return None
    if on_disk.is_relative_to(reported):
        return on_disk
    return reported if reported.is_relative_to(on_disk) else None


def _is_git_entry(path: Path) -> bool:
    """A repository directory with HEAD and objects, or a gitfile naming a git directory with HEAD."""
    if path.is_dir() and not path.is_symlink():
        return (path / "HEAD").is_file() and (path / "objects").is_dir()
    try:
        text = path.read_text() if path.is_file() and not path.is_symlink() else ""
    except OSError:
        return False
    prefix, _, target = text.strip().partition("gitdir:")
    return not prefix and bool(target.strip()) and ((path.parent / target.strip()) / "HEAD").is_file()


def _session_temporary_roots() -> tuple[Path, ...]:
    """Temporary directories the provider issued for this session; a general TMPDIR may be any shared tree."""
    parents = [
        Path(value).expanduser().resolve() for name in PROVIDER_TEMPORARY_VARIABLES if (value := os.environ.get(name))
    ]
    roots = [child for parent in parents for child in parent.glob(f"{PROVIDER_TEMPORARY_PREFIX}*") if child.is_dir()]
    general = os.environ.get("TMPDIR")
    if general and (root := Path(general).expanduser().resolve()).parent in SHARED_TEMPORARY_ROOTS:
        roots += [root] if root.name.startswith(PROVIDER_TEMPORARY_PREFIX) else []
    return tuple(
        root
        for root in roots
        if root not in SHARED_TEMPORARY_ROOTS and not PER_USER_TEMPORARY_ROOT.fullmatch(root.as_posix())
    )


def _is_safe_companion(item: shell_syntax.Command) -> bool:
    """Whether the segment is rm itself, or a listed read-only program or wrapper named bare with no assignment."""
    name = command_policy.canonical(item).arguments[0]
    if name == PROGRAM:
        return True
    bare = (
        not item.program_is_dynamic
        and item.arguments[0] == name
        and not shell_inspection.has_prefix_assignment(item.raw, name)
    )
    return bare and name in COMPANIONS | WRAPPERS


def _runs_a_system_program(item: shell_syntax.Command) -> bool:
    """A builtin the shell runs itself, or a root-owned system program run with no assignment before it.

    Behind an external wrapper even a builtin's name is looked up on PATH, and an assignment such as
    PATH or LD_PRELOAD before a call can change which program runs.
    """
    if item.arguments[0] in BUILTINS and not item.wrapper_depth:
        return not system_programs.inherits_execution_overrides()
    return not shell_inspection.has_prefix_assignment(item.raw, item.words[0]) and system_programs.is_system_program(
        item.arguments[0]
    )


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
    """Options and (operand, known only at run time) pairs; every word after `--` is an operand.

    A word that brace expansion or splitting can spread into several counts as known only at run time.
    """
    options: list[str] = []
    operands: list[tuple[str, bool]] = []
    ended = False
    for word, fixed_dynamic, spreading in zip(call.arguments[1:], call.dynamic[1:], call.spreading[1:], strict=True):
        dynamic = fixed_dynamic or spreading
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
    path = Path(word)
    if path.name in {"", ".", ".."}:
        return automation_paths.resolved_target(directory, word)
    parent = automation_paths.resolved_target(directory, str(path.parent))
    return parent / path.name if parent is not None else None


def _names_git_metadata(path: Path) -> bool:
    return any(part.casefold() == GIT_DIRECTORY for part in path.parts)
