"""Decide whether a command's words are literal enough for the rules marked literal_words."""

from pathlib import Path
import re

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
    """Allow literal calls and curl pipelines through known read-only filters; when unsure, ask."""
    if len(commands) > 1:
        return (
            commands[0].arguments[0] == "curl"
            and shell_inspection.is_plain_pipeline(command)
            and all(is_read_only_filter(item) for item in commands[1:])
            and allows_literal_rules(commands[0].raw, commands[:1])
        )
    if not commands or Path(commands[0].arguments[0]).name not in LITERAL_PROGRAMS:
        return False
    try:
        if not shell_syntax.is_one_simple_command(command):
            return False
        return has_literal_words(command)
    except shell_syntax.UnsupportedSyntax:
        return False


def has_literal_words(command: str) -> bool:
    """Whether no word can expand at run time: no parameter, arithmetic, command or process substitution, glob, or tilde."""
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
