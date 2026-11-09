"""Scan edited files with the registry's ast-grep rules and describe each finding for the agent."""

from collections.abc import Iterable, Mapping
import json
import os
from pathlib import Path
import shutil

from lib import process_runner
from lib.formatter_policy import Step


SCANNER = "ast-grep"
CONFIG_NAME = "sgconfig.yml"
DIRECTORY_VARIABLE = "AGENT_LINT_DIR"
FAILURE_OUTPUT_LINES = 8


def diagnostics(paths: Iterable[Path], environment: Mapping[str, str] = os.environ) -> tuple[str, ...]:
    """Describe rule findings in existing files; stay silent without a rules directory or the scanner.

    The rules directory is `AGENT_LINT_DIR`, else the `lint` directory next to the deployed `hooks` directory.
    It must hold the `sgconfig.yml` that names the rule directories. Findings are advice, so a scanner
    failure is reported as a message and never raised.
    """
    config = scanner_config(environment)
    files = [str(path) for path in paths if path.is_file()]
    if config is None or not files or shutil.which(SCANNER) is None:
        return ()
    step = Step("ast-grep scan", (SCANNER, "scan", "--config", str(config), "--json=stream", *files))
    try:
        result = process_runner.run_process(step, Path(files[0]), dict(environment))
    except OSError as error:
        return (f"Static rules failed\n{error}",)
    output = result.diagnostics.decode(errors="replace")
    found = tuple(message for line in output.splitlines() if (message := finding(line)))
    if found or (result.returncode in (0, 1) and not result.timed_out):
        return found
    return (failure(output, result.timed_out),)


def scanner_config(environment: Mapping[str, str]) -> Path | None:
    """Locate the scanner configuration of the rules directory, or None when it is not deployed."""
    default = Path(__file__).resolve().parents[2] / "lint"
    config = Path(environment.get(DIRECTORY_VARIABLE) or default) / CONFIG_NAME
    return config if config.is_file() else None


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
    reason = "timed out" if timed_out else "\n".join(output.strip().splitlines()[:FAILURE_OUTPUT_LINES])
    return f"Static rules failed\n{reason or 'No diagnostic output.'}"
