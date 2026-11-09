"""Hold every shell whose syntax is not bash's to review when it receives a script."""

from pathlib import Path

import hook_decision
from hook_decision import Verdict
import shell_syntax


def objection(commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask when such a shell receives a script; a deny rule that its visible text matches comes first."""
    item = next((item for item in commands if item.unreviewed), None)
    if item is None:
        return hook_decision.ALLOW
    preview = shell_syntax.command_preview(item.raw)
    return hook_decision.ask(
        f"Needs review: {Path(item.arguments[0]).name} runs a script in a syntax this inspection cannot "
        f"parse, so what it runs is unknown.\n\nCommand: {preview}",
        "foreign-shell",
    )
