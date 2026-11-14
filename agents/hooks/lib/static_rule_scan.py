"""Scan edited files with the ast-grep rules of the project that owns them and describe each finding."""

import json
import os
import shutil
from collections.abc import Iterable
from pathlib import Path

from lib import process_runner
from lib.formatter_policy import Step

SCANNER = "ast-grep"
CONFIG_NAME = "sgconfig.yml"
SHARED_CONFIG = Path(__file__).resolve().parent.parent / "lint" / CONFIG_NAME
FAILURE_OUTPUT_LINES = 8
TRUNCATED = "Static rule output truncated\nThe scanner output exceeded the size limit; some findings may be missing."


def diagnostics(paths: Iterable[Path]) -> tuple[str, ...]:
    """Describe rule findings in existing files; stay silent without any `sgconfig.yml` or the scanner.

    Each file is scanned with the shared rules shipped beside the hooks and with the nearest `sgconfig.yml` above
    it, so the rules and their tests stay native ast-grep files. `ast-grep --config` takes one file, hence two runs.
    Findings are advice: a scanner failure is reported as a message, never raised.
    """
    if shutil.which(SCANNER) is None:
        return ()
    by_scope: dict[tuple[Path, Path], list[str]] = {}
    for path in paths:
        if not path.is_file():
            continue
        for config in configs_for(path):
            root = scan_root(path, config)
            by_scope.setdefault((config, root), []).append(str(path.relative_to(root)))
    return tuple(message for (config, root), files in by_scope.items() for message in scan(config, root, files))


def scan_root(path: Path, config: Path) -> Path:
    """Pick the directory that the `files:` globs of a configuration match against.

    A project configuration matches paths relative to its own directory. The shared configuration matches paths
    relative to the repository, else the project, else the file, so directories above the repository, such as
    `~/common/`, stay out of the globs.
    """
    if config != SHARED_CONFIG:
        return config.parent
    repository = next((d for d in path.parents if (d / ".git").exists()), None)
    if repository is not None:
        return repository
    project = project_config(path)
    return project.parent if project is not None else path.parent


def configs_for(path: Path) -> tuple[Path, ...]:
    """Pick the shared config, then the project's own unless it is the same file."""
    candidates = (SHARED_CONFIG, project_config(path))
    found = {config.resolve(): config for config in candidates if config is not None and config.is_file()}
    return tuple(found.values())


def project_config(path: Path) -> Path | None:
    """Find the nearest ancestor `sgconfig.yml` of a file."""
    return next((c for directory in path.parents if (c := directory / CONFIG_NAME).is_file()), None)


def scan(config: Path, root: Path, files: list[str]) -> tuple[str, ...]:
    """Run the scanner once, from `root`, for files sharing one configuration."""
    step = Step("ast-grep scan", (SCANNER, "scan", "--config", str(config), "--json=stream", *files), cwd=root)
    try:
        result = process_runner.run_process(step, root / files[0], dict(os.environ))
    except OSError as error:
        return (f"Static rules failed\n{error}",)
    output = result.diagnostics.decode(errors="replace")
    found = tuple(message for line in output.splitlines() if (message := finding(line, root)))
    notes = (TRUNCATED,) if result.output_truncated else ()
    if result.timed_out or result.returncode not in (0, 1):
        notes += (failure(output, result.timed_out, root),)
    return found + notes


def finding(line: str, root: Path) -> str:
    """Format one JSON line of scanner output, or return an empty string for any other line."""
    try:
        record = json.loads(line)
        file = root / record["file"]
        message = f"Static rule {record['ruleId']} · {file}:{record['range']['start']['line'] + 1}"
        return f"{message}\n{record['message']}"
    except ValueError, KeyError, TypeError:
        return ""


def failure(output: str, timed_out: bool, root: Path) -> str:
    """Describe a scanner that produced no findings and did not finish normally."""
    lines = [line for line in output.strip().splitlines() if not finding(line, root)]
    reason = "timed out" if timed_out else "\n".join(lines[:FAILURE_OUTPUT_LINES])
    return f"Static rules failed\n{reason or 'No diagnostic output.'}"
