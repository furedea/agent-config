"""Commands whose words show they only read and print: they write no file and run no other program.

Only the words are judged here; whether the name runs the installed program, and where redirections
write, the caller checks.
"""

import re
from collections.abc import Sequence

FILTERS = frozenset(
    {"cat", "column", "cut", "echo", "false", "grep", "head", "jq", "ls", "nl", "printf", "pwd", "sleep"}
    | {"tail", "tr", "true", "wc"}
)
# Programs whose options or program text decide whether they write a file or run a program.
WORD_CHECKED = frozenset({"awk", "base64", "sed", "sort", "uniq"})
# Short sort options taking no value; o and the long --output and --compress-program write or run.
SORT_FLAGS = re.compile(r"-[bdfghiMnRrsuVcCz]+")
SORT_VALUED = re.compile(r"-[kt]|--(?:key|field-separator|buffer-size|parallel|sort|batch-size)(?:=|$)")
SORT_SEPARATE_VALUES = frozenset({"-k", "-t", "--key", "--field-separator"})
SORT_LONG = frozenset({"--check", "--ignore-case", "--numeric-sort", "--reverse", "--stable", "--unique"})
SORT_LONG |= {"--general-numeric-sort", "--human-numeric-sort", "--version-sort", "--zero-terminated"}
UNIQ_OPTIONS = re.compile(r"-[cdiuDz]+|--(?:count|repeated|ignore-case|unique|zero-terminated)")
# awk writes with `>` or `>>`, pipes to or from a command with `|`, runs one with system(), and gawk loads
# extensions with @load; a comparison using `>` asks too.
AWK_HAZARD = re.compile(r"[>|@]|system|getline")
SED_ADDRESS = r"(?:\d+|\$|/(?:[^/\\\n]|\\.)*/)"
SED_PRINT = re.compile(rf"(?:{SED_ADDRESS}(?:,{SED_ADDRESS})?)?p")
SED_SUBSTITUTE = re.compile(r"s/(?:[^/\\\n]|\\.)*/(?:[^/\\\n]|\\.)*/[gpI0-9]*")
BASE64_DECODE = frozenset({"-d", "-D", "--decode"})
SED_FLAGS = frozenset({"-n", "-E", "-r", "--quiet", "--silent"})


def writes_nothing(arguments: Sequence[str], dynamic: Sequence[bool]) -> bool:
    """Whether a call's words show it writes no file and runs no other program.

    A word known only at run time could be an option such as sort's -o, so it is allowed only to a filter.
    """
    name, *rest = arguments
    if name in FILTERS:
        return True
    if name not in WORD_CHECKED or any(dynamic):
        return False
    checks = {"awk": _awk_reads, "sed": _sed_prints, "sort": _sort_reads, "uniq": _uniq_reads}
    checks["base64"] = _base64_decodes
    return checks[name](rest)


def _base64_decodes(arguments: list[str]) -> bool:
    """A base64 call decoding its standard input; macOS base64 writes to a file named with -o."""
    return set(arguments) <= BASE64_DECODE


def _sort_reads(arguments: list[str]) -> bool:
    """A sort call with options that only order its output; -o writes a file and --compress-program runs one."""
    takes_value = False
    for word in arguments:
        if word == "--" and not takes_value:
            return True
        if not (takes_value or _is_ordering_option(word)):
            return False
        takes_value = not takes_value and word in SORT_SEPARATE_VALUES
    return True


def _is_ordering_option(word: str) -> bool:
    if not word.startswith("-") or word == "-":
        return True
    return bool(SORT_FLAGS.fullmatch(word) or SORT_VALUED.match(word)) or word in SORT_LONG


def _uniq_reads(arguments: list[str]) -> bool:
    """Uniq writes to its second operand, so it reads only with at most one."""
    operands = [word for word in arguments if not UNIQ_OPTIONS.fullmatch(word)]
    return len(operands) <= 1 and not any(word.startswith("-") and word != "-" for word in operands)


def _awk_reads(arguments: list[str]) -> bool:
    """Awk with only -F and -v options, a program given in the line, and nothing in it that writes or runs."""
    index = 0
    while index < len(arguments) and arguments[index].startswith("-") and arguments[index] != "-":
        option = arguments[index]
        if option == "--":
            index += 1
            break
        if option not in {"-F", "-v"} and not option.startswith(("-F", "-v")):
            return False
        index += 2 if option in {"-F", "-v"} else 1
    return index < len(arguments) and not AWK_HAZARD.search(arguments[index])


def _sed_prints(arguments: list[str]) -> bool:
    """Sed printing lines by number or pattern, or substituting without a w or e flag, never in place."""
    scripts, operands, words = [], [], iter(arguments)
    for word in words:
        if word in {"-e", "--expression"}:
            scripts.append(next(words, ""))
        elif word.startswith("-") and word != "-" and word not in SED_FLAGS:
            return False
        elif word not in SED_FLAGS:
            operands.append(word)
    scripts = scripts or operands[:1]
    return bool(scripts) and all(_is_print_script(script) for script in scripts)


def _is_print_script(script: str) -> bool:
    commands = script.strip().split(";")
    return all(SED_PRINT.fullmatch(item.strip()) or SED_SUBSTITUTE.fullmatch(item.strip()) for item in commands)
