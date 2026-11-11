"""Decide whether the shell that runs a command is known to expand it with zsh's default options."""

import os
import re
from collections.abc import Iterator
from dataclasses import replace
from itertools import combinations
from pathlib import Path

import shell_syntax
from shell_words import ENVIRONMENT_NAMES, SIMPLE_PARAMETER, vanishes_when_empty

# Only Claude Code's Bash tool is confirmed to run commands in $SHELL, which the hook inherits; a
# payload without a provider comes straight from Claude Code. Codex and the other providers choose
# their own shell, which the hook cannot see, so they keep the shell-independent reading.
CONFIRMED_PROVIDERS = frozenset({"", "claude"})
# More words that may vanish than this, and the guard stays with its shell-independent reading.
MAX_VANISHING_WORDS = 4


def as_run_by_zsh(
    payload: dict, command: str, commands: tuple[shell_syntax.Command, ...]
) -> tuple[shell_syntax.Command, ...]:
    """Read unquoted environment variables as zsh runs them, or leave the commands when the shell is not certain.

    An unquoted `$TMPDIR`, `$HOME`, `$PWD`, or `$USER` is one word, or none if empty, but only while the command
    mentions the name nowhere but in expansions: an assignment, declaration, `read`, `unset`, `trap`, or function
    could make it an array or change its value, however it is spelled.
    """
    if not _is_zsh(payload):
        return commands
    names = frozenset(name for name in ENVIRONMENT_NAMES if not _is_named_beyond_expansions(name, command))
    return tuple(_as_run_by_zsh(item, names) for item in commands)


def _is_named_beyond_expansions(name: str, command: str) -> bool:
    """Whether the command, with its quotes and escapes removed as the shell does, names the variable otherwise."""
    escaped = re.escape(name)
    spelled = re.sub(r"[\\'\"]", "", re.sub(r"\$(?=['\"])", "", command.replace("\\\n", "")))
    rest = re.sub(rf"\${escaped}\b|\$\{{{escaped}\}}", "", spelled)
    return bool(re.search(rf"(?<![\w$]){escaped}(?!\w)", rest))


def _is_zsh(payload: dict) -> bool:
    if (payload.get("provider") or "") not in CONFIRMED_PROVIDERS:
        return False
    executable = os.environ.get("CLAUDE_CODE_SHELL") or os.environ.get("SHELL") or ""
    return Path(executable).name == "zsh"


def _as_run_by_zsh(item: shell_syntax.Command, names: frozenset[str]) -> shell_syntax.Command:
    """Read the command's unquoted variables among `names` as one word each, or none if empty.

    Only a command the outer shell itself runs: a script another shell runs is read as before,
    and so is a command with more vanishing words than the guard enumerates.
    """
    one_word = tuple(
        spreading and not zsh_spreading and set(SIMPLE_PARAMETER.findall(word)) <= names
        for word, spreading, zsh_spreading in zip(item.words, item.spreading, item.zsh_spreading, strict=True)
    )
    vanishing = tuple(flag and vanishes_when_empty(word) for word, flag in zip(item.words, one_word, strict=True))
    if item.wrapper_depth or sum(vanishing) > MAX_VANISHING_WORDS:
        return item
    spreading = tuple(spreads and not flag for spreads, flag in zip(item.spreading, one_word, strict=True))
    return replace(item, spreading=spreading, vanishing=vanishing)


def vanishing_variants(item: shell_syntax.Command) -> Iterator[shell_syntax.Command]:
    """The command, then it again without each combination of the words that vanish when empty."""
    yield item
    positions = [index for index, flagged in enumerate(item.vanishing) if flagged and index]
    for size in range(1, len(positions) + 1):
        for dropped in combinations(positions, size):
            yield _without(item, dropped)


def _without(item: shell_syntax.Command, dropped: tuple[int, ...]) -> shell_syntax.Command:
    def kept(values: tuple) -> tuple:
        return tuple(value for index, value in enumerate(values) if index not in dropped)

    return replace(
        item,
        arguments=kept(item.arguments),
        words=kept(item.words),
        quoted_words=kept(item.quoted_words),
        dynamic=kept(item.dynamic),
        spreading=kept(item.spreading),
        zsh_spreading=kept(item.zsh_spreading),
        vanishing=kept(item.vanishing),
    )
