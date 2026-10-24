"""Name the paths a shell command touches, expanding braces and globs the way the shell would."""

from collections.abc import Iterator
import glob
from itertools import islice
import os
from pathlib import Path
import re
import shlex

import shell_syntax


GLOB = re.compile(r"[*?[]")
# Brace expansion multiplies; past this many words the command needs review rather than stall the hook.
BRACE_EXPANSION_LIMIT = 256
HOME_VARIABLE = re.compile(r"\$(?:HOME\b|\{HOME\})")


class UnexpandableGlob(ValueError):
    """A glob whose expansion depends on a value known only at run time."""


def command_paths(command: str) -> list[str]:
    """Return every argument, redirection, and assignment value, each glob replaced by the files it matches now.

    A glob expands against the files that exist at hook time in every directory the command may
    have reached, so a file the same command creates earlier is not seen. Its content can become
    secret only by naming a secret file literally, which is judged as written.
    """
    directories: tuple[Path | None, ...] = (Path.cwd(),)
    paths: list[str] = []
    for item in shell_syntax.parse(command):
        directories = shell_syntax.reached_directories(directories, item)
        static = [argument for argument, dynamic in zip(item.arguments, item.dynamic, strict=True) if not dynamic]
        paths += with_variants(static)
        for word in with_variants(shell_patterns(item)):
            paths += expanded_paths(word, directories) if GLOB.search(word) else [word]
    return paths


def shell_patterns(item: shell_syntax.Command) -> list[str]:
    """The words the shell may expand: run-time arguments without their quotes, and redirection targets.

    A quoted glob is a static argument, passed to the program as written.
    """
    dynamic = (argument for argument, dynamic in zip(item.arguments, item.dynamic, strict=True) if dynamic)
    return [*item.redirections, *(unquoted for argument in dynamic for unquoted in unquoted_words(argument))]


def with_variants(words: list[str]) -> list[str]:
    """Add each word's brace expansions and each assignment's value."""
    words = words + [expanded for word in words if "{" in word for expanded in brace_expansions(word)]
    return words + [word.partition("=")[2] for word in words if "=" in word]


def expanded_paths(pattern: str, directories: tuple[Path | None, ...]) -> list[str]:
    """Expand a glob as the shell would: from the home directory, from the root, or from each reachable directory."""
    pattern = HOME_VARIABLE.sub(lambda _: str(Path.home()), pattern)
    if "$" in pattern or "`" in pattern:
        raise UnexpandableGlob(f"cannot expand {pattern}, whose value is known only at run time")
    if pattern.startswith("~"):
        return glob.glob(os.path.expanduser(pattern))
    if os.path.isabs(pattern):
        return glob.glob(pattern)
    if None in directories:
        raise UnexpandableGlob(f"cannot expand {pattern} in a directory known only at run time")
    return [path for directory in directories if directory for path in glob.glob(pattern, root_dir=directory)]


def unquoted_words(source: str) -> list[str]:
    """Drop the quotes of a run-time word's source text, so a partly quoted glob such as ".en"* is judged as .en*."""
    try:
        return shlex.split(source)
    except ValueError:
        return []


def brace_expansions(word: str) -> list[str]:
    """Expand comma braces as the shell does before globbing, so {.env,x} is judged as .env and x."""
    words = list(islice(brace_words(word), BRACE_EXPANSION_LIMIT + 1))
    if len(words) > BRACE_EXPANSION_LIMIT:
        raise UnexpandableGlob(f"{word} expands to more than {BRACE_EXPANSION_LIMIT} words")
    return words


def brace_words(word: str) -> Iterator[str]:
    starts = (start for start, character in enumerate(word) if character == "{")
    groups = ((start, group) for start in starts if (group := brace_group(word, start)) is not None)
    if (first := next(groups, None)) is None:
        yield word
        return
    start, (end, alternatives) = first
    for alternative in alternatives:
        yield from brace_words(word[:start] + alternative + word[end + 1 :])


def brace_group(word: str, start: int) -> tuple[int, list[str]] | None:
    """Locate the brace closing the one at start and split its top-level alternatives; None without a comma."""
    depth, alternatives, first = 0, [], start + 1
    for index in range(start, len(word)):
        character = word[index]
        if character == "{":
            depth += 1
        elif character == "}" and (depth := depth - 1) == 0:
            return (index, [*alternatives, word[first:index]]) if alternatives else None
        elif character == "," and depth == 1:
            alternatives.append(word[first:index])
            first = index + 1
    return None
