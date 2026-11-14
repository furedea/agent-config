"""Ask when a dependency change runs with settings the guard cannot read.

Dependency changes run unprompted because they rewrite only the project's manifests and lock files.
An environment variable such as npm_config_global or PNPM_HOME, set on the call, through env, or by
an export or sourced file in the same command, can send the install outside the project instead,
and the parsed words do not show it.
"""

import re
from pathlib import Path

import command_policy
import hook_decision
import shell_inspection
import shell_syntax
from hook_decision import Verdict

# (program, subcommand) of the dependency changes the shared prefixes allow.
DEPENDENCY_CHANGES = frozenset(
    {
        ("pnpm", "add"),
        ("uv", "add"),
        ("uv", "lock"),
        ("cargo", "add"),
        ("cargo", "update"),
        ("go", "get"),
        ("go", "mod"),
        ("nix", "flake"),
    }
)
# Declarations the parser keeps out of its commands, which set variables for the rest of the command.
DECLARATION = re.compile(r"(^|[\s;&|(){}])(export|declare|typeset|readonly|local)(\s|$)")
# Programs that set variables or run a file of settings for the rest of the command.
SETTINGS_PROGRAMS = frozenset(
    {"env", "export", "declare", "typeset", "readonly", "local", "set", "source", ".", "eval"}
)


def objection(command: str, commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask when a dependency change carries an assignment, runs behind a wrapper, or shares a settings command."""
    changes = [item for item in commands if _is_dependency_change(item)]
    if not changes:
        return hook_decision.ALLOW
    settings = any(_program(item) in SETTINGS_PROGRAMS for item in commands) or DECLARATION.search(
        shell_inspection.text_outside_single_quotes(command)
    )
    preview = shell_syntax.command_preview(changes[0].raw)
    if settings or any(item.wrapper_depth or _has_assignment(item) for item in changes):
        return hook_decision.ask(
            "Needs review: a dependency change runs with environment settings the guard cannot read, which can "
            f"install outside the project.\n\nCommand: {preview}",
            _program(changes[0]),
        )
    return hook_decision.ALLOW


def _is_dependency_change(item: shell_syntax.Command) -> bool:
    arguments = command_policy.canonical(item).arguments
    return any((arguments[0], word) in DEPENDENCY_CHANGES for word in arguments[1:])


def _program(item: shell_syntax.Command) -> str:
    return Path(item.arguments[0]).name


def _has_assignment(item: shell_syntax.Command) -> bool:
    return not item.raw.lstrip().startswith(item.words[0])
