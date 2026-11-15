"""Scan edited files with the ast-grep rules of the project that owns them and describe each finding."""

import dataclasses
import functools
import json
import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from lib import process_runner, trusted_owners
from lib.formatter_policy import Step

SCANNER = "ast-grep"
CONFIG_NAME = "sgconfig.yml"
HOOK_ROOT = Path(__file__).resolve().parent.parent
SHARED_CONFIG = HOOK_ROOT / "lint" / CONFIG_NAME
TRUSTED_OWNERS_FILE = HOOK_ROOT / "rules" / "trusted_owners.json"
FAILURE_OUTPUT_LINES = 8
BLOCKING_SEVERITY = "error"
# ast-grep exits 1 exactly when it found a finding of severity error.
ERRORS_FOUND = 1
TRUNCATED_ERRORS = (
    "Static rule errors truncated\nThe scanner found errors, but its output exceeded the size limit before them. "
    "Run `ast-grep scan` on the edited files to see them."
)
TRUNCATED = "Static rule output truncated\nThe scanner output exceeded the size limit; some findings may be missing."


@dataclass(frozen=True, slots=True)
class Report:
    """What the agent is told after an edit: `errors` must be fixed before it goes on, `advice` need not."""

    advice: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __add__(self, other: Report) -> Report:
        return Report(self.advice + other.advice, self.errors + other.errors)


def diagnostics(paths: Iterable[Path]) -> Report:
    """Describe rule findings in existing files; stay silent without any `sgconfig.yml` or the scanner.

    Each file is scanned with the shared rules shipped beside the hooks and with the nearest `sgconfig.yml` above
    it, so the rules and their tests stay native ast-grep files. `ast-grep --config` takes one file, hence two runs.
    A finding of severity error is an error the agent must fix; other findings and scanner failures are advice.
    """
    if shutil.which(SCANNER) is None:
        return Report()
    shared_rules_apply_to = functools.cache(shared_rules_apply)
    by_scope: dict[tuple[Path, Path], list[str]] = {}
    for path in paths:
        if not path.is_file():
            continue
        for config in configs_for(path, shared_rules_apply_to(repository_root(path))):
            root = scan_root(path, config)
            by_scope.setdefault((config, root), []).append(str(path.relative_to(root)))
    return sum((scan(config, root, files) for (config, root), files in by_scope.items()), Report())


def scan_root(path: Path, config: Path) -> Path:
    """Pick the directory that the `files:` globs of a configuration match against.

    A project configuration matches paths relative to its own directory. The shared configuration runs only in a
    checkout and matches paths relative to it, so directories above the repository, such as `~/common/`, stay out
    of the globs.
    """
    if config != SHARED_CONFIG:
        return config.parent
    return repository_root(path) or path.parent


def configs_for(path: Path, shared: bool) -> tuple[Path, ...]:
    """Pick the shared config when it applies, then the project's own unless it is the same file."""
    candidates = (SHARED_CONFIG if shared else None, project_config(path))
    found = {config.resolve(): config for config in candidates if config is not None and config.is_file()}
    return tuple(found.values())


def repository_root(path: Path) -> Path | None:
    """The checkout a file belongs to, or None outside any repository."""
    return next((directory for directory in path.parents if (directory / ".git").exists()), None)


def shared_rules_apply(root: Path | None) -> bool:
    """Whether the shared rules run in a checkout: they are the owner's style, so only for trusted owners.

    Any other project's own style takes precedence; a missing or unreadable trusted owners file trusts no one. Only
    the owner is asked: whether the repository is a fork matters to what model rules may read, not to whose style
    applies, and its network lookup would slow every edit and turn the rules off when it gets no answer.
    """
    if root is None:
        return False
    configured = Path(os.environ.get("AGENT_TRUSTED_OWNERS", str(TRUSTED_OWNERS_FILE)))
    try:
        owners = dataclasses.replace(trusted_owners.load(configured), exclude_forks=False)
    except ValueError:
        return False
    return trusted_owners.distrust_reason(root, owners) is None


def project_config(path: Path) -> Path | None:
    """Find the nearest ancestor `sgconfig.yml` of a file."""
    return next((c for directory in path.parents if (c := directory / CONFIG_NAME).is_file()), None)


def scan(config: Path, root: Path, files: list[str]) -> Report:
    """Run the scanner once, from `root`, for files sharing one configuration."""
    step = Step("ast-grep scan", (SCANNER, "scan", "--config", str(config), "--json=stream", "--", *files), cwd=root)
    try:
        result = process_runner.run_process(step, root / files[0], dict(os.environ))
    except OSError as error:
        return Report(advice=(f"Static rules failed\n{error}",))
    output = result.diagnostics.decode(errors="replace")
    found = [(record, message) for line in output.splitlines() for record, message in finding(line, root)]
    notes = (TRUNCATED,) if result.output_truncated else ()
    if result.timed_out or result.returncode not in (0, 1):
        return Report(advice=(*(message for _, message in found), *notes, failure(output, result.timed_out, root)))
    errors = tuple(message for record, message in found if record.get("severity") == BLOCKING_SEVERITY)
    advice = tuple(message for record, message in found if record.get("severity") != BLOCKING_SEVERITY)
    if result.output_truncated and result.returncode == ERRORS_FOUND and not errors:
        errors = (TRUNCATED_ERRORS,)
    return Report(advice + notes, errors)


def finding(line: str, root: Path) -> tuple[tuple[dict, str], ...]:
    """Parse one JSON line of scanner output into its record and message, or nothing for any other line.

    The message names the rule and location, then why the code is wrong and, from the rule's `note`, the fix.
    """
    try:
        record = json.loads(line)
        file = root / record["file"]
        message = f"Static rule {record['ruleId']} · {file}:{record['range']['start']['line'] + 1}"
        message += f"\n{record['message']}"
    except ValueError, KeyError, TypeError:
        return ()
    note = record.get("note")
    return ((record, f"{message}\nFix: {note.strip()}" if isinstance(note, str) and note.strip() else message),)


def failure(output: str, timed_out: bool, root: Path) -> str:
    """Describe a scanner that produced no findings and did not finish normally."""
    lines = [line for line in output.strip().splitlines() if not finding(line, root)]
    reason = "timed out" if timed_out else "\n".join(lines[:FAILURE_OUTPUT_LINES])
    return f"Static rules failed\n{reason or 'No diagnostic output.'}"
