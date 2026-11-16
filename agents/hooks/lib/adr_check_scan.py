"""Check the ADR directory of an edited ADR with `adr-check` and describe what it finds."""

import os
import shutil
from collections.abc import Iterable
from pathlib import Path

from lib import process_runner
from lib.formatter_policy import Step

COMMAND = "adr-check"
ADR_DIRECTORY = ("docs", "adr")
OUTPUT_LINES = 24


def diagnostics(paths: Iterable[Path]) -> tuple[str, ...]:
    """Describe the findings of each edited ADR's directory once; stay silent without the command.

    A finding can sit in a file other than the edited one (a reference that no longer resolves), so the whole
    directory is checked. Findings are advice: a failed run is reported as a message, never raised.
    """
    if shutil.which(COMMAND) is None:
        return ()
    directories = dict.fromkeys(path.parent for path in paths if is_adr_file(path))
    return tuple(message for directory in directories if (message := check(directory)))


def is_adr_file(path: Path) -> bool:
    """Whether `path` is an existing Markdown file directly inside a `docs/adr` directory."""
    return path.suffix == ".md" and path.is_file() and path.parent.parts[-2:] == ADR_DIRECTORY


def check(directory: Path) -> str:
    """Run the command on one directory; an empty string means no finding."""
    step = Step(COMMAND, (COMMAND, str(directory)), cwd=directory)
    try:
        result = process_runner.run_process(step, directory, dict(os.environ))
    except OSError as error:
        return f"ADR check failed\n{error}"
    output = result.diagnostics.decode(errors="replace").strip()
    if result.timed_out:
        return "ADR check failed\ntimed out"
    if result.returncode == 0:
        return ""
    lines = output.splitlines()
    shown = "\n".join(lines[:OUTPUT_LINES])
    omitted = f"\n[{len(lines) - OUTPUT_LINES} more lines omitted]" if len(lines) > OUTPUT_LINES else ""
    heading = "ADR check" if result.returncode == 1 else "ADR check failed"
    return f"{heading}\n{shown or 'No diagnostic output.'}{omitted}"
