"""Let browser and desktop automation run unprompted only with options known to stay in their lane.

The lists come from the upstream CLIs (agent-browser `cli/src/commands.rs` and `cli/src/flags.rs`,
agent-desktop `src/cli_args`) and keep only options that neither read nor write a path nor reach
another process or session. Any other option asks, so an option a CLI update adds asks until listed.
"""

import command_policy
import hook_decision
from hook_decision import Verdict
import shell_syntax


BROWSER_GLOBAL = frozenset({"--json", "--headed", "--session"})
BROWSER = {
    "a11y": frozenset({"--json", "--selector", "--tags", "-s"}),
    "click": frozenset({"--human", "--new-tab"}),
    "console": frozenset({"--clear"}),
    "cookies": frozenset(
        {"--domain", "--expires", "--http-only", "--httpOnly", "--path", "--same-site", "--sameSite", "--secure"}
        | {"--url"}
    ),
    "drag": frozenset({"--human"}),
    "errors": frozenset({"--clear"}),
    "eval": frozenset({"--base64", "-b"}),
    "find": frozenset({"--exact", "--name"}),
    "mouse": frozenset({"--duration", "--human", "--seed", "--steps"}),
    "network": frozenset(
        {"--abort", "--allow-origin", "--body", "--clear", "--content", "--filter", "--method", "--status", "--type"}
        | {"--resource-type", "--resource-types"}
    ),
    "profiler": frozenset({"--categories"}),
    "react": frozenset({"--json", "--only-dynamic", "--raw-json"}),
    "read": frozenset({"--filter", "--json", "--llms", "--outline", "--raw", "--require-md", "--timeout"}),
    "screenshot": frozenset({"--full"}),
    "scroll": frozenset({"--selector", "-s"}),
    "snapshot": frozenset(
        {"--compact", "--cursor", "--depth", "--full", "--interactive", "--selector", "--urls"}
        | {"-C", "-c", "-d", "-i", "-s", "-u"}
    ),
    "tab": frozenset({"--label"}),
    "type": frozenset({"--clear", "--delay"}),
    "vitals": frozenset({"--json"}),
    "wait": frozenset({"--fn", "--load", "--text", "--timeout", "--url", "-f", "-l", "-t", "-u"}),
}
DESKTOP_GLOBAL = frozenset({"--session", "--help", "-h", "--version", "-V"})
DESKTOP_WAIT_FOR = frozenset({"--wait-for", "-w", "--wait-for-gone", "--wait-timeout"})
DESKTOP_REF_ACTION = frozenset({"--timeout-ms"}) | DESKTOP_WAIT_FOR
DESKTOP_APP = frozenset({"--app"})
DESKTOP = {
    "snapshot": DESKTOP_APP
    | DESKTOP_WAIT_FOR
    | {"--compact", "--force-electron-a11y", "--include-bounds", "--interactive-only", "-i", "--max-depth"}
    | {"--root", "--skeleton", "--timeout-ms"},
    "find": DESKTOP_APP
    | {"--count", "--description", "--exact", "--first", "--last", "--limit", "--name", "--native-id", "--nth"}
    | {"--role", "--root", "--state", "--text", "--timeout-ms", "--value"},
    "screenshot": DESKTOP_APP,
    "list-surfaces": DESKTOP_APP,
    "resize-window": DESKTOP_APP | {"--width", "--height"},
    "move-window": DESKTOP_APP | {"--x", "--y"},
    "focus-window": DESKTOP_APP | {"--title"},
    "minimize": DESKTOP_APP,
    "maximize": DESKTOP_APP,
    "restore": DESKTOP_APP,
    **dict.fromkeys(
        (
            "click",
            "double-click",
            "triple-click",
            "right-click",
            "clear",
            "focus",
            "toggle",
            "check",
            "uncheck",
            "expand",
            "collapse",
            "scroll-to",
            "set-value",
            "select",
        ),
        DESKTOP_REF_ACTION,
    ),
    "type": DESKTOP_REF_ACTION | {"--interval-ms"},
    "scroll": DESKTOP_REF_ACTION | {"--amount", "--direction"},
    "get": frozenset({"--property"}),
    "is": frozenset({"--property"}),
    "list-apps": DESKTOP_APP | {"--timeout-ms"},
    "list-windows": DESKTOP_APP | {"--timeout-ms"},
    "list-notifications": DESKTOP_APP | {"--limit", "--text"},
    "dismiss-notification": DESKTOP_APP | {"--expected-app", "--expected-title"},
    "dismiss-all-notifications": DESKTOP_APP,
    "notification-action": frozenset({"--expected-app", "--expected-title"}),
    "clipboard-get": frozenset({"--format"}),
    "wait": DESKTOP_APP
    | {"--action", "--count", "--element", "--event", "--menu", "--menu-closed", "--notification"}
    | {"--predicate", "--text", "--timeout", "--value", "--window"},
}
OPTIONS = {"agent-browser": (BROWSER_GLOBAL, BROWSER), "agent-desktop": (DESKTOP_GLOBAL, DESKTOP)}


def objection(commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask when an automation call holds an option its subcommand does not list, `--name=value` included."""
    calls = [candidate for item in commands if (candidate := command_policy.canonical(item)).arguments[0] in OPTIONS]
    option = next((option for call in calls if (option := unlisted_option(call.arguments))), "")
    if not option:
        return hook_decision.ALLOW
    return hook_decision.ask(
        f"Needs review: '{option}' is not a listed option for this {calls[0].arguments[0]} subcommand; an "
        f"unlisted option may read or write a file or reach another session.\n\n"
        f"Command: {shell_syntax.command_preview(commands[0].raw)}",
        calls[0].arguments[0],
    )


def unlisted_option(arguments: tuple[str, ...]) -> str:
    """The first word starting with `-` that neither the program nor its subcommand lists, or an empty string."""
    global_options, subcommands = OPTIONS[arguments[0]]
    words = arguments[1:]
    while words[:1] in (("--json",), ("--headed",), ("--session",)) and arguments[0] == "agent-browser":
        words = words[2:] if words[0] == "--session" else words[1:]
    listed = global_options | subcommands.get(words[0] if words else "", frozenset())
    return next(
        (word for word in arguments[1:] if word.startswith("-") and word.partition("=")[0] not in listed),
        "",
    )
