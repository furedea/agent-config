"""Scan edited files with the ast-grep rules of the project that owns them and describe each finding."""

from collections.abc import Iterable
import json
import os
from pathlib import Path
import shutil

from lib import process_runner
from lib.formatter_policy import Step


SCANNER = "ast-grep"
CONFIG_NAME = "sgconfig.yml"
FAILURE_OUTPUT_LINES = 8
TRUNCATED = "Static rule output truncated\nThe scanner output exceeded the size limit; some findings may be missing."


def diagnostics(paths: Iterable[Path]) -> tuple[str, ...]:
    """Describe rule findings in existing files; stay silent without an `sgconfig.yml` or the scanner.

    Each file is scanned with the nearest `sgconfig.yml` above it, so the rules and their tests stay native
    ast-grep files of the project. Findings are advice: a scanner failure is reported as a message, never raised.
    """
    if shutil.which(SCANNER) is None:
        return ()
    by_config: dict[Path, list[str]] = {}
    for path in paths:
        if path.is_file() and (config := project_config(path)) is not None:
            by_config.setdefault(config, []).append(str(path))
    return tuple(message for config, files in by_config.items() for message in scan(config, files))


def project_config(path: Path) -> Path | None:
    """Find the nearest ancestor `sgconfig.yml` of a file."""
    return next((c for directory in path.parents if (c := directory / CONFIG_NAME).is_file()), None)


def scan(config: Path, files: list[str]) -> tuple[str, ...]:
    """Run the scanner once for files sharing one configuration."""
    step = Step("ast-grep scan", (SCANNER, "scan", "--config", str(config), "--json=stream", *files))
    try:
        result = process_runner.run_process(step, Path(files[0]), dict(os.environ))
    except OSError as error:
        return (f"Static rules failed\n{error}",)
    output = result.diagnostics.decode(errors="replace")
    found = tuple(message for line in output.splitlines() if (message := finding(line)))
    notes = (TRUNCATED,) if result.output_truncated else ()
    if result.timed_out or result.returncode not in (0, 1):
        notes += (failure(output, result.timed_out),)
    return found + notes


def finding(line: str) -> str:
    """Format one JSON line of scanner output, or return an empty string for any other line."""
    try:
        record = json.loads(line)
        message = f"Static rule {record['ruleId']} · {record['file']}:{record['range']['start']['line'] + 1}"
        return f"{message}\n{record['message']}"
    except ValueError, KeyError, TypeError:
        return ""


def failure(output: str, timed_out: bool) -> str:
    """Describe a scanner that produced no findings and did not finish normally."""
    lines = [line for line in output.strip().splitlines() if not finding(line)]
    reason = "timed out" if timed_out else "\n".join(lines[:FAILURE_OUTPUT_LINES])
    return f"Static rules failed\n{reason or 'No diagnostic output.'}"
