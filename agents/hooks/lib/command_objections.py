"""Every objection the command guard can raise: per segment, per command line, and per named script."""

import os
import re
from pathlib import Path
from typing import Protocol

import automation_paths
import command_policy
import herdr_grammar
import hook_decision
import literal_words
import shell_inspection
import shell_syntax
from hook_decision import Verdict

REQUEST_PROGRAMS = frozenset({"curl", "wget"})
REMOTE_REASON = (
    "Needs review: remote curl/wget can send local data. Read web pages with the web-fetch tool, "
    "or use gh api / nix store prefetch-file for exact values and files."
)
SAFE_WRITE_OUT = re.compile(
    r"(?:%\{(?:http_code|time_total|time_connect|time_starttransfer|size_download|content_type|url_effective|remote_ip)\}"
    r"|\\n|[A-Za-z0-9 :=_.,/-])*"
)
REQUEST_SETTINGS = re.compile(r"proxy|curlrc|wgetrc|curl_home|(^|[^a-z0-9_])(home|xdg_config_home)=", re.IGNORECASE)


class Policy(Protocol):
    """The part of the guard's loaded policy the objections read; the guard owns the concrete type."""

    @property
    def prefixes(self) -> list[dict]:
        """Generated permission prefixes, each carrying its decision."""
        ...

    @property
    def rules(self) -> list[dict]:
        """Regex rules of the guard kind being evaluated."""
        ...

    @property
    def listing_rules(self) -> list[dict]:
        """Rules that list the exact forms a governed or pinned program may run unprompted."""
        ...


def objection(kind: str, item: shell_syntax.Command, policy: Policy) -> Verdict:
    """Judge one segment by its own words and by its canonical program and subcommand.

    Rules see only the command's words: redirections stay inside the sandbox, and heredoc bodies
    are data, not commands, and so is an argument containing whitespace.
    """
    candidate = command_policy.canonical(item)
    preview = shell_syntax.command_preview(item.raw)
    if kind == "forbidden":
        return forbidden_objection(item, candidate, policy)
    if (verdict := wrapped_ask_objection(candidate, policy.prefixes, preview)).decision != "allow":
        return verdict
    return governed_objection(candidate, policy, preview)


def wrapped_ask_objection(candidate: shell_syntax.Command, prefixes: list[dict], preview: str) -> Verdict:
    """Ask for an ask-prefix command that runs behind a wrapper or inside a shell script.

    The provider matches an ask prefix only against the command it sees, so a wrapper or a shell -c
    hides the prefix from it; the hook decides itself.
    """
    asked = command_policy.prefix_rule(candidate.arguments, prefixes, "ask") if candidate.wrapper_depth else None
    if asked is None:
        return hook_decision.ALLOW
    prefix = " ".join(asked["prefix"])
    return hook_decision.ask(
        f"Needs review: '{prefix}' runs behind a wrapper or inside a shell script, where the permission rules "
        f"do not see it.\n\nCommand: {preview}",
        prefix,
    )


def is_listed(candidate: shell_syntax.Command, rules: list[dict]) -> bool:
    """Whether a rule lists the form; Herdr's watching commands must also keep to their documented options.

    An automation program's form must also be listed with its quotes removed, so a quoted word can
    hide neither a subcommand nor an option from the rule's exceptions.
    """
    if not command_policy.regex_reason(candidate.static_words_text, rules):
        return False
    if candidate.arguments[0] in automation_paths.PROGRAMS and not command_policy.regex_reason(
        " ".join(candidate.arguments), rules
    ):
        return False
    if candidate.arguments[0] == "curl" and any(
        (option in {"-w", "--write-out"} and not SAFE_WRITE_OUT.fullmatch(value))
        or (option == "-H" and ("\r" in value or "\n" in value))
        for option, value in zip(candidate.arguments, candidate.arguments[1:], strict=False)
    ):
        return False
    return not herdr_grammar.is_watch_command(candidate.arguments) or herdr_grammar.is_documented(candidate.arguments)


def forbidden_objection(item: shell_syntax.Command, candidate: shell_syntax.Command, policy: Policy) -> Verdict:
    """Deny only: a literal deny prefix or pattern wins even beside a run-time argument."""
    rules = command_policy.unscoped_rules(policy.rules)
    flagged = (command_policy.without_option_values(item), command_policy.without_option_values(candidate))
    matched = (
        command_policy.regex_reason(flagged[0].command_words_text, rules)
        or command_policy.regex_reason(flagged[1].command_words_text, rules)
        or command_policy.regex_reason(flagged[0].command_arguments_text, rules)
        or command_policy.regex_reason(flagged[1].command_arguments_text, rules)
        or command_policy.argument_reason(candidate.arguments, policy.rules)
    )
    reason = command_policy.prefix_reason(candidate.arguments, policy.prefixes, "deny") or matched
    if not reason:
        return hook_decision.ALLOW
    preview = shell_syntax.command_preview(item.raw)
    return hook_decision.deny(
        f"BLOCKED: forbidden command: {reason}.\n\nCommand: {preview}\n\n{hook_decision.REVIEW_HINT}"
    )


def governed_objection(candidate: shell_syntax.Command, policy: Policy, preview: str) -> Verdict:
    """Review only programs whose effects reach past the sandbox; the sandbox confines every other form.

    A run-time word counts as a plain placeholder, so it passes only where any value would, and a
    command that can hide an option from the rules, or takes more arguments from xargs, asks: a
    quoted option, or a word that may split into several, such as an unquoted expansion.
    """
    prefixes, rules = policy.prefixes, policy.rules
    if candidate.program_is_dynamic or candidate.arguments[0] not in command_policy.governed_programs(rules):
        return hook_decision.ALLOW
    if candidate.arguments[0] == "herdr" and herdr_grammar.has_global_option(candidate.arguments):
        return hook_decision.ask(
            f"Needs review: a Herdr global option such as --session shifts the words after it.\n\nCommand: {preview}",
            "herdr",
        )
    governed = command_policy.prefix_rule(candidate.arguments, prefixes, "allow")
    if (
        governed is None
        and candidate.arguments[0] in command_policy.asking_programs(rules)
        and command_policy.prefix_rule(candidate.arguments, prefixes, "ask") is None
    ):
        return hook_decision.ask(
            f"Needs review: '{candidate.arguments[0]}' reaches host files and networks outside the sandbox, "
            f"and only read-only inspection runs without approval.\n\nCommand: {preview}",
            candidate.arguments[0],
        )
    if governed is None or (
        not candidate.appends_input and not candidate.hides_options and is_listed(candidate, policy.listing_rules)
    ):
        return hook_decision.ALLOW
    prefix = " ".join(governed["prefix"])
    if candidate.arguments[0] in REQUEST_PROGRAMS:
        return hook_decision.ask(f"{REMOTE_REASON}\n\nCommand: {preview}", prefix)
    return hook_decision.ask(
        f"Needs review: command not in allowlist. '{prefix}' is approved, but not in this form.\n\nCommand: {preview}",
        prefix,
    )


def settings_objection(command: str, commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask when a curl or wget call shares its command with settings that could send it elsewhere."""
    requests = any(command_policy.canonical(item).arguments[0] in REQUEST_PROGRAMS for item in commands)
    if not requests or not REQUEST_SETTINGS.search(command):
        return hook_decision.ALLOW
    return hook_decision.ask(f"{REMOTE_REASON}\n\nCommand: {shell_syntax.command_preview(command)}", "settings")


def pinned_program_objection(command: str, commands: tuple[shell_syntax.Command, ...], policy: Policy) -> Verdict:
    """A program whose rule pins a path runs unprompted only as the one command of the line.

    It must run by that path, in a listed form.

    A PATH lookup, an assignment, a wrapper, another statement, or an expansion can change what runs
    after this check, so each of them, the bare name included, asks.
    """
    pinned = command_policy.pinned_programs(policy.rules)
    calls = [(name, item) for item in commands if (name := pinned_name(item)) in pinned]
    if not calls:
        return hook_decision.ALLOW
    try:
        single = shell_syntax.is_one_simple_command(command) and literal_words.has_literal_words(command)
    except shell_syntax.UnsupportedSyntax:
        single = False
    offending = next(
        (name for name, item in calls if not single or not is_listed_pinned_call(item, pinned, policy)), None
    )
    if offending is None:
        return hook_decision.ALLOW
    return hook_decision.ask(
        f"Needs review: '{offending}' runs without approval only as the single command {pinned[offending]} "
        "<arguments>, with literal words only (no expansion), no assignment, wrapper, or other statement, and "
        f"only while that file is an executable regular file.\n\nCommand: {shell_syntax.command_preview(command)}",
        offending,
    )


def pinned_name(item: shell_syntax.Command) -> str:
    """The program a call names, as the rules do; zsh's `=name` is a PATH lookup of `name`."""
    return Path(item.arguments[0]).name.removeprefix("=")


def is_listed_pinned_call(item: shell_syntax.Command, pinned: dict[str, str], policy: Policy) -> bool:
    """A pinned program is its own allowlist: a project cannot add provider prefixes, so only a listed form passes."""
    name = pinned_name(item)
    candidate = item.rebased(1, (name,))
    return (
        _is_pinned_call(item, pinned[name])
        and not candidate.hides_options
        and is_listed(candidate, policy.listing_rules)
    )


def _is_pinned_call(item: shell_syntax.Command, path: str) -> bool:
    program = Path(path)
    return (
        item.arguments[0] == path
        and not item.wrapper_depth
        and not item.program_is_dynamic
        and program.is_file()
        and os.access(program, os.X_OK)
    )


def cleanup_objection(command: str, commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Match the entire cleanup call before segment parsing can hide a wrapper or shell operator."""
    cleanup = any(
        Path(item.arguments[0]).name == "cleanup_worktrees.py"
        or (
            (
                Path(item.arguments[0]).name.startswith("python")
                or Path(item.arguments[0]).name in {"uv", "bash", "sh", "zsh"}
            )
            and any(Path(argument).name == "cleanup_worktrees.py" for argument in item.arguments[1:])
        )
        for item in commands
    )
    if not cleanup:
        return hook_decision.ALLOW
    pattern = re.escape(str(Path.home() / ".claude/hooks/cleanup_worktrees.py")) + r"( --dry-run)?"
    if re.fullmatch(pattern, command):
        return hook_decision.ALLOW
    return hook_decision.ask(
        "Needs review: run cleanup_worktrees.py as one bare call or with --dry-run only.", "cleanup_worktrees.py"
    )


def companion_objection(command: str, commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Keep companion execution in the single-call form matched by its sandbox exclusion."""
    cache = "/.claude/plugins/cache/openai-codex/codex/"
    roots = tuple(root + cache for root in ("~", str(Path.home())))
    companion = any(
        Path(item.arguments[0]).name == "codex-companion.mjs"
        or (
            Path(item.arguments[0]).name == "node"
            and any(
                Path(argument).name == "codex-companion.mjs" or argument.startswith(roots)
                for argument in item.arguments[1:]
            )
        )
        for item in commands
    )
    if not companion:
        return hook_decision.ALLOW
    literal_text = shell_inspection.text_outside_single_quotes(command)
    if "$" in literal_text or "`" in literal_text:
        return hook_decision.deny(
            "BLOCKED: forbidden command: task or focus text must not contain a dollar sign or backtick, "
            "because the sandbox exclusion does not match a command with expansions."
        )
    try:
        simple = len(commands) == 1 and shell_syntax.is_one_simple_command(command)
    except shell_syntax.UnsupportedSyntax:
        simple = False
    if simple:
        arguments = commands[0].arguments
        script = re.escape(str(Path.home()) + cache) + r"[0-9]+\.[0-9]+\.[0-9]+/scripts/codex-companion\.mjs"
        if len(arguments) >= 2 and arguments[0] == "node" and re.fullmatch(script, arguments[1]):
            return hook_decision.ALLOW
        return hook_decision.deny(
            "BLOCKED: forbidden command: expected node followed by the exact plugin cache script "
            "at codex/<digits>.<digits>.<digits>/scripts/codex-companion.mjs."
        )
    return hook_decision.deny(
        'BLOCKED: forbidden command: run it as one command starting with node "<plugin path>/codex-companion.mjs", '
        "pass --cwd <dir> instead of cd, and no pipes, redirects, &&, or assignments, "
        "because the sandbox exclusion matches only that form."
    )
