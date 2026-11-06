"""Load command policy once and preserve the existing POSIX ERE matching contract."""

from collections.abc import Sequence
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from dataclasses import replace

import git_safety
import shell_syntax


# Characters a URL parser drops anywhere in a URL, so a scheme split by them still loads.
URL_IGNORED_CHARACTERS = str.maketrans("", "", "\t\n\r")


def regex_matches(pattern: str, value: str, insensitive: bool = False) -> bool:
    """Use the existing system regex engine instead of silently changing regex dialects."""
    return any_regex_matches((pattern,), value, insensitive)


def any_regex_matches(patterns: Sequence[str], value: str, insensitive: bool = False) -> bool:
    """Spawn one grep for a whole pattern set; process start-up, not matching, dominates each decision.

    Line breaks become spaces, so the value is one line for any grep: anchors span a whole shell
    segment, and a newline inside a quoted argument can neither hide a segment from an anchored
    rule nor satisfy one by itself. GNU and BSD grep then agree, whichever is first on PATH.
    """
    if not patterns:
        return False
    flags = "-qiE" if insensitive else "-qE"
    selectors = [argument for pattern in patterns for argument in ("-e", pattern)]
    result = subprocess.run(
        ["grep", flags, *selectors],
        input=re.sub(r"[\r\n]", " ", value),
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode > 1:
        raise ValueError("invalid POSIX extended regex rule")
    return result.returncode == 0


def load_rules(path: Path, prefixes: bool = False) -> list[dict]:
    """Validate policy at its boundary, including regex syntax before evaluating commands."""
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("invalid version")
        rules = data.get("rules")
        if not isinstance(rules, list) or (not prefixes and not rules):
            raise ValueError("invalid rules")
        for rule in rules:
            validate_rule(rule, prefixes)
        if not prefixes:
            any_regex_matches(all_patterns(rules), "")
        return rules
    except (OSError, ValueError, TypeError) as error:
        raise ValueError(f"invalid command policy: {path}") from error


def validate_rule(rule: object, prefixes: bool) -> None:
    if not isinstance(rule, dict) or not isinstance(rule.get("justification"), str) or not rule["justification"]:
        raise ValueError("missing justification")
    values = rule.get("prefix" if prefixes else "patterns")
    if not is_name_list(values):
        raise ValueError("invalid command rule")
    if prefixes and rule.get("decision") not in {"allow", "ask", "deny"}:
        raise ValueError("invalid decision")
    if not prefixes and "programs" in rule and not is_name_list(rule["programs"]):
        raise ValueError("invalid governed program list")
    if not prefixes and "exceptions" in rule and not is_name_list(rule["exceptions"]):
        raise ValueError("invalid exception list")
    if not prefixes and not isinstance(rule.get("literal_words", False), bool):
        raise ValueError("invalid literal word flag")
    if not prefixes and not isinstance(rule.get("ask_unlisted", False), bool):
        raise ValueError("invalid ask-unlisted flag")
    if not prefixes and "program_path" in rule:
        validate_program_path(rule)


def validate_program_path(rule: dict) -> None:
    """A pinned path is a normalized absolute file path, and the one program the rule governs is named by it."""
    path = rule["program_path"]
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or any(character in path for character in " \t\n*?[]{}$`\\'\"~")
    ):
        raise ValueError("invalid program path")
    if str(PurePosixPath(path)) != path or ".." in PurePosixPath(path).parts or path == "/":
        raise ValueError("program path is not normalized")
    if rule.get("programs") != [PurePosixPath(path).name]:
        raise ValueError("program path must pin the one program the rule governs")


def is_name_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item for item in value)


def literal_rules(rules: list[dict], *, literal: bool) -> list[dict]:
    """The rules that apply only when every word of the command is literal, or the others."""
    return [rule for rule in rules if rule.get("literal_words", False) is literal]


def governed_programs(rules: list[dict]) -> frozenset[str]:
    """Programs whose effects reach past the sandbox, so only their listed forms pass unreviewed."""
    return frozenset(program for rule in rules for program in rule.get("programs", ()))


def asking_programs(rules: list[dict]) -> frozenset[str]:
    """Governed programs that ask for every form no allow prefix lists, not only for unlisted allowed forms.

    A prefix ask rule cannot express this: providers let an ask or deny prefix override the allow
    prefixes beneath it, so a catch-all would stop the listed forms from running unprompted.
    """
    return frozenset(program for rule in rules if rule.get("ask_unlisted", False) for program in rule["programs"])


def unscoped_rules(rules: list[dict]) -> list[dict]:
    """Forbidden rules that read every command's words."""
    return [rule for rule in rules if "programs" not in rule]


def argument_reason(arguments: tuple[str, ...], rules: list[dict]) -> str:
    """The rationale of the first forbidden rule scoped to this program that its decoded arguments match.

    Such a rule reads the arguments as the program receives them, quotes removed and prose included,
    and ignores case, because the app names and URL schemes it names are case-insensitive. Tabs and
    line breaks are dropped first, as a URL parser drops them, so `fi<TAB>le:` still reads as `file:`.
    """
    text = " ".join(arguments).translate(URL_IGNORED_CHARACTERS)
    return next(
        (
            rule["justification"]
            for rule in rules
            if arguments[0] in rule.get("programs", ())
            and any_regex_matches(rule["patterns"], text, insensitive=True)
            and not any_regex_matches(rule.get("exceptions", ()), text, insensitive=True)
        ),
        "",
    )


def project_root() -> Path | None:
    """The Git root that owns the project's policy."""
    start = os.environ.get("AGENT_PROJECT_DIR", os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    try:
        root = subprocess.check_output(
            ["git", "-C", start, "rev-parse", "--show-toplevel"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except OSError, subprocess.CalledProcessError:
        return None
    return Path(root)


def project_file(root: Path, name: str) -> Path | None:
    """Locate optional project policy under its Git root."""
    path = root / ".agents/hooks/rules" / name
    return path if path.is_file() else None


def canonical(command: shell_syntax.Command) -> shell_syntax.Command:
    """Judge a program by its name and Git by its subcommand, not by install path or global options."""
    name = Path(command.arguments[0]).name
    if name != "git":
        return command.rebased(1, (name,))
    globals_, _ = git_safety.git_arguments(command.arguments)
    return command.rebased(1 + len(globals_), ("git",))


# git commit options that take a value: the next word, or the rest of the same short-option bundle.
COMMIT_VALUED_SHORT = frozenset("mFCct")
COMMIT_VALUED_LONG = frozenset(
    {"--message", "--file", "--reuse-message", "--reedit-message", "--template", "--author", "--date", "--cleanup"}
    | {"--fixup", "--squash", "--trailer", "--pathspec-from-file"}
)


def without_option_values(command: shell_syntax.Command) -> shell_syntax.Command:
    """The command with each git commit option value as a placeholder, in its words and its decoded arguments.

    Flag rules read the rest: a value such as the message in `-m "--no-verify"` is data, not a flag.
    """
    valued = commit_option_values(command.arguments)
    masked = tuple("_" if index in valued else word for index, word in enumerate(command.words))
    masked_arguments = tuple("_" if index in valued else word for index, word in enumerate(command.arguments))
    return replace(command, words=masked, arguments=masked_arguments)


def commit_option_values(arguments: tuple[str, ...]) -> frozenset[int]:
    """Indexes of the words a git commit consumes as option values, so `-m "--no-verify"` stays a message."""
    names = [Path(argument).name for argument in arguments]
    if "commit" not in arguments or "git" not in names[: arguments.index("commit")]:
        return frozenset()
    consumed: set[int] = set()
    index = arguments.index("commit") + 1
    while index < len(arguments):
        token = arguments[index]
        if index in consumed or token == "--":
            break
        if token in COMMIT_VALUED_LONG or (not token.startswith("--") and valued_short(token)):
            consumed.add(index + 1)
            index += 1
        index += 1
    return frozenset(consumed)


def valued_short(token: str) -> bool:
    """Whether a short-option bundle ends in an option whose value is the next word."""
    if not token.startswith("-") or len(token) < 2:
        return False
    for position, letter in enumerate(token[1:], 1):
        if letter in COMMIT_VALUED_SHORT:
            return position == len(token) - 1
    return False


def prefix_rule(arguments: tuple[str, ...], rules: list[dict], decision: str) -> dict | None:
    """Match complete parsed arguments rather than flattening away token boundaries."""
    return next(
        (
            rule
            for rule in rules
            if rule["decision"] == decision and arguments[: len(rule["prefix"])] == tuple(rule["prefix"])
        ),
        None,
    )


def prefix_reason(arguments: tuple[str, ...], rules: list[dict], decision: str) -> str:
    rule = prefix_rule(arguments, rules, decision)
    return rule["justification"] if rule else ""


def regex_reason(raw: str, rules: list[dict]) -> str:
    """Return the first applicable rule's stated rationale, asking grep once before locating that rule."""
    raw = re.sub(r"\s+(?:2>&1|2>/dev/null|>&2)\s*$", "", raw.strip())
    if not any_regex_matches(all_patterns(rules), raw):
        return ""
    return next((rule["justification"] for rule in rules if rule_matches(rule, raw)), "")


def rule_matches(rule: dict, raw: str) -> bool:
    """A rule applies when a pattern matches and none of its narrow exceptions does."""
    return any_regex_matches(rule.get("patterns", ()), raw) and not any_regex_matches(rule.get("exceptions", ()), raw)


def all_patterns(rules: list[dict]) -> list[str]:
    return [pattern for rule in rules for pattern in rule.get("patterns", ())]


def pinned_programs(rules: list[dict]) -> dict[str, str]:
    """Programs that may run unprompted only by one absolute path, with that path."""
    pinned: dict[str, str] = {}
    for rule in rules:
        if "program_path" not in rule:
            continue
        program, path = rule["programs"][0], rule["program_path"]
        if pinned.setdefault(program, path) != path:
            raise ValueError(f"conflicting program_path for {program}: {pinned[program]} and {path}")
    return pinned
