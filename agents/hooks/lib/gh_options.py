"""Read a gh call's words as pflag does, and tell which run-time words may hide an option or a value.

A value option takes the next word whatever it holds, short options may bundle, and options may follow
positional arguments. A word the guard cannot read the way gh will makes the call unclassifiable.
"""

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import shell_syntax
import shell_words

# A word whose only expansions are plain named parameters beside literal text. In a call that is the
# whole line nothing assigns them, so each holds what the harness environment gave the shell; the
# literal text keeps the word from vanishing when a parameter is empty, so it stays one word.
PARAMETER = r"\$(?:[A-Za-z_][A-Za-z0-9_]*(?![A-Za-z0-9_\[])|\{[A-Za-z_][A-Za-z0-9_]*\})"
PLAIN_PARAMETER_WORD = re.compile(rf"""(?:[A-Za-z0-9_./:@=,+%#-]|{PARAMETER}|'[^']*'|"(?:[^"$`\\!]|{PARAMETER})*")+""")
# A run-time word starting with one of these cannot start with a dash.
LITERAL_START = re.compile(r"[\"']?[A-Za-z0-9_./:@=,+%#]")


class UnclassifiableError(ValueError):
    """The guard cannot tell what a gh call does; the classifier returns it as an Unclassified value."""


@dataclass(frozen=True, slots=True)
class Word:
    """One argument as gh receives it, with what the shell may still do to it."""

    value: str
    source: str
    dynamic: bool = False
    spreading: bool = False

    @property
    def may_be_option(self) -> bool:
        """Whether gh could read the word as an option: it is one, may split, or may start with a dash at run time."""
        if self.spreading:
            return True
        return not LITERAL_START.match(self.source) if self.dynamic else self.value.startswith("-")


@dataclass(frozen=True, slots=True)
class OptionTable:
    """The options a command accepts: those taking a value, and flags taking none."""

    values: frozenset[str]
    flags: frozenset[str]


@dataclass(frozen=True, slots=True)
class OptionScan:
    """A call's arguments read against its option table."""

    options: tuple[tuple[str, Word], ...]
    positionals: tuple[Word, ...]
    flags: frozenset[str]

    def values_of(self, names: frozenset[str]) -> tuple[Word, ...]:
        """The value words given to any of the named options, in order."""
        return tuple(word for option, word in self.options if option in names)


def stays_one_word(source: str) -> bool:
    """Whether an unquoted word whose expansions are plain parameters beside literal text stays one word."""
    return bool(PLAIN_PARAMETER_WORD.fullmatch(source)) and bool(re.sub(PARAMETER, "", source).strip("\"'"))


def scan(words: tuple[Word, ...], table: OptionTable) -> OptionScan:
    """Read options as pflag does; an option the table does not name makes the call unclassified."""
    options: list[tuple[str, Word]] = []
    positionals: list[Word] = []
    found: set[str] = set()
    index = 0
    while index < len(words):
        word = words[index]
        index += 1
        if word.value == "--" and not word.dynamic:
            positionals += words[index:]
            break
        if word.dynamic or not word.value.startswith("-") or word.value == "-":
            positionals.append(word)
            continue
        names, value, consumed = _option(word, words[index : index + 1], table)
        found |= names
        index += consumed
        if value is not None:
            options.append((next(iter(names & table.values)), value))
    return OptionScan(tuple(options), tuple(positionals), frozenset(found))


def _option(word: Word, following: tuple[Word, ...], table: OptionTable) -> tuple[frozenset[str], Word | None, int]:
    """The option names a word sets, its value word if one takes a value, and how many further words that used."""
    if word.value.startswith("--"):
        name, equals, inline = word.value.partition("=")
        if name in table.flags and not equals:
            return frozenset({name}), None, 0
        _require_value_option(name, table)
        return (frozenset({name}), Word(inline, inline), 0) if equals else _with_following(name, following)
    names: set[str] = set()
    for position, letter in enumerate(word.value[1:], 1):
        name = "-" + letter
        if name in table.flags:
            names.add(name)
            continue
        _require_value_option(name, table)
        rest = word.value[position + 1 :]
        if not rest:
            return frozenset(names | {name}), *_with_following(name, following)[1:]
        value = rest.removeprefix("=")
        return frozenset(names | {name}), Word(value, value), 0
    return frozenset(names), None, 0


def _require_value_option(name: str, table: OptionTable) -> None:
    if name not in table.values:
        raise UnclassifiableError(f"option {name} is not in the gh operation table for this command")


def _with_following(name: str, following: tuple[Word, ...]) -> tuple[frozenset[str], Word, int]:
    if not following:
        raise UnclassifiableError(f"option {name} has no value")
    return frozenset({name}), following[0], 1


def has_parameter(source: str) -> bool:
    """Whether a word expands a parameter other than HOME outside any command substitution.

    A substitution's commands are judged on their own and its text is part of the command, so a body
    built by one, such as a quoted heredoc through cat, hides no value of its own.
    """
    tree = shell_syntax.syntax_tree(": " + source)
    return any(
        node.get("Type") == "ParamExp" and not shell_words.is_home_parameter(node)
        for node in shell_words.word_nodes(tree)
    )


def is_one_substitution(source: str) -> bool:
    """Whether a word is exactly one command substitution, so no output joins other text the scan saw apart."""
    tree = shell_syntax.syntax_tree(": " + source)
    arguments = tree.get("Stmts", [{}])[0].get("Cmd", {}).get("Args", [])
    parts = arguments[1].get("Parts", []) if len(arguments) == 2 else []
    if len(parts) == 1 and parts[0].get("Type") == "DblQuoted":
        parts = parts[0].get("Parts", [])
    if len(parts) != 1 or parts[0].get("Type") != "CmdSubst":
        return False
    # One plain call inside, so no second command, pipe, or list adds output after the first.
    statements = parts[0].get("Stmts", [])
    return len(statements) == 1 and (statements[0].get("Cmd") or {}).get("Type") == "CallExpr"


def is_plain_subdirectory(words: tuple[Word, ...]) -> bool:
    """Whether the last word names a new literal relative directory below the working directory, none of it hidden.

    Artifacts an untrusted run produced must not land in .git, a tool's dot directory, outside the checkout,
    or over existing files that a later command may run.
    """
    if not words or words[-1].dynamic or Path(words[-1].value).exists():
        return False
    parts = PurePosixPath(words[-1].value).parts
    return (
        bool(parts)
        and not PurePosixPath(words[-1].value).is_absolute()
        and not any(part.startswith((".", "~")) for part in parts)
    )
