"""Decide whether a command's words are literal enough for the rules marked literal_words."""

import re
from pathlib import Path

import shell_inspection
import shell_syntax

# Settings that can send a request to a local server somewhere else: a proxy, or another configuration file.
# The only programs the literal_words rules govern; through any wrapper they get main's rules, or no
# rule at all for curl and wget.
LITERAL_PROGRAMS = frozenset({"agent-browser", "agent-desktop", "curl", "gh", "herdr", "wget"})
# Characters through which any shell may expand or run something, and a word starting with `=` (zsh
# looks it up on PATH); a command holding one anywhere outside quotes, in the program name, an
# assignment, or a redirect included, gets no literal_words rule.
EXPANDING_TEXT = re.compile(r"[$`~*?\[\]{}]|\\\n|(?:^|[ \t])=")
# Inside double quotes the shell still expands only these, and `!` for history expansion; glob
# characters there are literal.
DOUBLE_QUOTE_EXPANDING_TEXT = re.compile(r"[$`\\!]")
# Filter words must stay literal even with zsh extended_glob; quote everything else with single quotes.
FILTER_LITERAL_TEXT = re.compile(r"[A-Za-z0-9_./:=,%+ \t\n-]*")


def allows_literal_rules(command: str, commands: tuple[shell_syntax.Command, ...]) -> bool:
    """Allow literal calls, and `&&` lists of them with pipelines through known read-only filters; when unsure, ask."""
    if not commands or any(item.wrapper_depth for item in commands):
        return False
    try:
        lengths = shell_inspection.plain_and_list_shape(command)
        if lengths is None or sum(lengths) != len(commands) or not has_literal_words(command):
            return False
    except shell_syntax.UnsupportedSyntaxError:
        return False
    pipelines, start = [], 0
    for length in lengths:
        pipelines.append(commands[start : start + length])
        start += length
    return all(is_literal_pipeline(pipeline) for pipeline in pipelines)


def is_literal_pipeline(pipeline: tuple[shell_syntax.Command, ...]) -> bool:
    """A literal-program call, followed only by known read-only filters."""
    head, *filters = pipeline
    return Path(head.arguments[0]).name in LITERAL_PROGRAMS and all(is_read_only_filter(item) for item in filters)


def has_literal_words(command: str) -> bool:
    """Whether no word can expand at run time.

    That means no parameter, arithmetic, command or process substitution, glob, or tilde.
    """
    return not (
        EXPANDING_TEXT.search(shell_inspection.text_outside_quotes(command))
        or DOUBLE_QUOTE_EXPANDING_TEXT.search(shell_inspection.double_quoted_text(command))
    )


def is_read_only_filter(command: shell_syntax.Command) -> bool:
    """List only known stdin-only forms; unknown options and jq programs ask."""
    if (
        command.wrapper_depth
        or command.has_dynamic_words
        or command.hides_options
        or not FILTER_LITERAL_TEXT.fullmatch(shell_inspection.text_outside_single_quotes(command.raw))
    ):
        return False
    program, *arguments = command.arguments
    text = " ".join(arguments)
    if program == "jq":
        return bool(re.fullmatch(r"(-[rceCMS]+ )*\.(?:[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)?", text))
    if program in {"head", "tail"}:
        return bool(re.fullmatch(r"(?:(?:-[nc] |--(?:lines|bytes)=)[0-9]+|-[0-9]+)?", text))
    if program == "wc":
        return all(re.fullmatch(r"-[lwcmL]+", argument) for argument in arguments)
    if program == "grep":
        while arguments and re.fullmatch(r"-[ivnEcFowqx]+", arguments[0]):
            arguments.pop(0)
        return len(arguments) == 1 and not arguments[0].startswith("-")
    return False
