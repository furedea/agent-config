"""Decide whether the shell that runs a command is known to expand it with zsh's default options."""

import os
import re
from collections.abc import Iterator
from dataclasses import replace
from itertools import combinations
from pathlib import Path

import shell_inspection
import shell_syntax
from shell_words import vanishes_when_empty

# Only Claude Code's Bash tool is confirmed to run commands in $SHELL, which the hook inherits; a
# payload without a provider comes straight from Claude Code. Codex and the other providers choose
# their own shell, which the hook cannot see, so they keep the shell-independent reading.
CONFIRMED_PROVIDERS = frozenset({"", "claude"})
# Commands that can change what an unquoted variable expands to: an option, an array or association,
# another emulation, or code and definitions the hook does not read.
EXPANSION_CHANGING_PROGRAMS = frozenset(
    {
        *"alias autoload builtin emulate eval float functions integer mapfile private read readarray set setopt"
        " shopt source unsetopt zmodload".split(),
        ".",
    }
)
# The parser reads these as declarations, not calls; `export` and `readonly` stay scalar unless `=(` shows.
DECLARATIONS = frozenset({"declare", "local", "typeset"})
# More words that may vanish than this, and the guard stays with its shell-independent reading.
MAX_VANISHING_WORDS = 4
# `name=(...)`, `name+=(...)`, and `name[index]=...` make a variable an array.
ARRAY_ASSIGNMENT = re.compile(r"\+?=\(|\]\+?=")


def as_run_by_zsh(
    payload: dict, command: str, commands: tuple[shell_syntax.Command, ...]
) -> tuple[shell_syntax.Command, ...]:
    """Read each command as zsh's defaults run it, or unchanged when the shell or its options are not certain."""
    if not _is_zsh(payload) or _may_change_expansion(command, commands):
        return commands
    return tuple(_as_run_by_zsh(item) for item in commands)


def _is_zsh(payload: dict) -> bool:
    if (payload.get("provider") or "") not in CONFIRMED_PROVIDERS:
        return False
    executable = os.environ.get("CLAUDE_CODE_SHELL") or os.environ.get("SHELL") or ""
    return Path(executable).name == "zsh"


def _may_change_expansion(command: str, commands: tuple[shell_syntax.Command, ...]) -> bool:
    return (
        any(
            item.program_is_dynamic or Path(item.arguments[0]).name in EXPANSION_CHANGING_PROGRAMS for item in commands
        )
        or bool(ARRAY_ASSIGNMENT.search(shell_inspection.text_outside_quotes(command)))
        or any(
            node.get("Type") == "DeclClause" and node.get("Variant", {}).get("Value") in DECLARATIONS
            for node in shell_syntax.nodes(shell_syntax.syntax_tree(command))
        )
    )


def _as_run_by_zsh(item: shell_syntax.Command) -> shell_syntax.Command:
    """Read the command's unquoted simple variables as one word each, or none if empty.

    Only a command the outer shell itself runs: a script another shell runs is read as before,
    and so is a command with more vanishing words than the guard enumerates.
    """
    vanishing = tuple(
        spreading and not zsh_spreading and vanishes_when_empty(word)
        for word, spreading, zsh_spreading in zip(item.words, item.spreading, item.zsh_spreading, strict=True)
    )
    if item.wrapper_depth or sum(vanishing) > MAX_VANISHING_WORDS:
        return item
    return replace(item, spreading=item.zsh_spreading, vanishing=vanishing)


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
