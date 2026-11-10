"""Run `jev-lint review` over a session's changes, within a cap, a lock and a deadline.

The process boundary is the only place that touches the model: `jev-lint` is started directly and `op` injects its key,
so the hook handles only the service-account token, and only in the environment of the `op` child.
"""

import json
import os
import shutil
import signal
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from model_rules_credentials import Credentials
from model_rules_outcome import Finding, Judgement, Plan, Prevented
from session_store import LockTimeoutError, StateError, file_lock, private_directory

REVIEWER = "jev-lint"
LAUNCHER = "op"
SUBJECT_CAP = 20
PLAN_TIMEOUT_SECONDS = 20.0
JUDGE_TIMEOUT_SECONDS = 60.0
LOCK_TIMEOUT_SECONDS = 30.0
OUTPUT_LIMIT_BYTES = 8 * 1024 * 1024
# Nothing else is passed on: TYPESAFE_BASE_URL or JEV_LINT_CACHE would redirect the code or the cache.
ENVIRONMENT_ALLOWLIST = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "XDG_STATE_HOME", "TMPDIR")
TOKEN_VARIABLE = "OP_SERVICE_ACCOUNT_TOKEN"


@dataclass(frozen=True, slots=True)
class Deadline:
    """A point in monotonic time that every step of one run must respect."""

    expires_at: float

    @classmethod
    def after(cls, seconds: float) -> Deadline:
        """A deadline `seconds` from now."""
        return cls(time.monotonic() + seconds)

    def remaining(self, limit: float) -> float:
        """The time left, at most `limit`; zero or less means the budget is spent."""
        return min(limit, self.expires_at - time.monotonic())


@dataclass(frozen=True, slots=True)
class Review:
    """One `jev-lint review` of a repository, judged by the model rules in `rules`.

    With a `base` it reviews the commits made since that commit; without one it reviews the uncommitted changes and
    the files git does not track yet. `jev-lint` has no single mode for both, so a session needs one review of each.
    `paths` limits a review to those files; a review that applies the cap names its own subset instead.
    """

    root: Path
    base: str | None
    rules: Path
    cache: Path
    paths: tuple[str, ...] = ()

    def plan(self, deadline: Deadline, cap: int) -> Plan | Prevented:
        """Count the subjects without asking the model, and keep the files whose subjects fit `cap`."""
        output = _Child((REVIEWER, *self._arguments("--dry-run"), *self.paths), _environment(), self.root).run(
            deadline.remaining(PLAN_TIMEOUT_SECONDS)
        )
        if isinstance(output, Prevented):
            return output
        try:
            return _capped_plan(json.loads(output), cap)
        except ValueError, KeyError, TypeError, AttributeError:
            return Prevented(f"{REVIEWER} printed a plan that cannot be read")

    def judge(self, plan: Plan, credentials: Credentials, deadline: Deadline) -> Judgement | Prevented:
        """Ask the model about the planned subjects, with the verdict cache shared by every session."""
        try:
            private_directory(self.cache.parent)
            with file_lock(self.cache.parent / ".lock", timeout=max(0.0, deadline.remaining(LOCK_TIMEOUT_SECONDS))):
                arguments = (
                    LAUNCHER,
                    "run",
                    "--environment",
                    credentials.environment,
                    "--",
                    REVIEWER,
                    *self._arguments(),
                    *(plan.paths or self.paths),
                )
                child = _Child(arguments, _environment({TOKEN_VARIABLE: credentials.token}), self.root)
                output = child.run(deadline.remaining(JUDGE_TIMEOUT_SECONDS))
        except LockTimeoutError:
            return Prevented("another session holds the verdict cache lock")
        except (OSError, StateError) as error:
            return Prevented(f"the verdict cache directory is unusable: {error}")
        if isinstance(output, Prevented):
            return output
        return _judgement(output, plan)

    def _arguments(self, *extra: str) -> tuple[str, ...]:
        base = ("--base", self.base) if self.base else ()
        return (
            "review",
            "--json",
            *extra,
            "--no-config",
            "--fail-on",
            "error",
            *base,
            "-R",
            str(self.rules),
            "-c",
            str(self.cache),
        )


def review_all(reviews: tuple[Review, ...], credentials: Credentials, deadline: Deadline) -> Judgement | Prevented:
    """Judge each review in turn, sharing one cap of SUBJECT_CAP subjects among them."""
    combined = Judgement(())
    cap = SUBJECT_CAP
    for review in reviews:
        plan = review.plan(deadline, cap)
        if isinstance(plan, Prevented):
            return plan
        cap = max(0, cap - plan.cost)
        outcome = review.judge(plan, credentials, deadline) if plan.judged else _unjudged(plan)
        if isinstance(outcome, Prevented):
            return outcome
        combined = combined.combined(outcome)
    return combined


def is_installed() -> Prevented | None:
    """None when both programs the run needs are on PATH, otherwise the missing one."""
    for program in (REVIEWER, LAUNCHER):
        if shutil.which(program) is None:
            return Prevented(f"{program} is not installed")
    return None


def cache_path(state_directory: Path) -> Path:
    """Where the shared verdict cache lives: under the agent state directory, outside every repository."""
    return state_directory.parent / "model-rules" / "verdicts.json"


def _environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    allowed = {name: os.environ[name] for name in ENVIRONMENT_ALLOWLIST if name in os.environ}
    return {**allowed, **(extra or {})}


@dataclass(frozen=True, slots=True)
class _Child:
    """A process to run to the end: its argv, its whole environment, and where it runs."""

    arguments: tuple[str, ...]
    environment: dict[str, str]
    cwd: Path

    def run(self, timeout: float) -> bytes | Prevented:
        """Run it, killing its whole process group at the deadline; stderr is discarded and never surfaced."""
        program = self.arguments[0]
        if timeout <= 0:
            return Prevented("the Stop hook has no time left for the model rules")
        try:
            process = subprocess.Popen(
                self.arguments,
                cwd=self.cwd,
                env=self.environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return Prevented(f"{program} could not be started")
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            return Prevented(f"{program} timed out after {timeout:.0f}s")
        if process.returncode != 0:
            return Prevented(f"{program} exited with status {process.returncode}")
        if len(output) > OUTPUT_LIMIT_BYTES:
            return Prevented(f"{program} printed more than {OUTPUT_LIMIT_BYTES // (1024 * 1024)} MiB")
        return output


def _unjudged(plan: Plan) -> Judgement:
    return Judgement((), plan.subjects, plan.skipped_files, plan.skipped_subjects)


def _capped_plan(report: dict, cap: int) -> Plan:
    subjects, cached = _count(report, "subjects"), _count(report, "cached")
    if subjects - cached <= cap:
        return Plan((), subjects, subjects - cached)
    per_file: dict[str, int] = {}
    for batch in report["batches"]:
        per_file[batch["file"]] = per_file.get(batch["file"], 0) + _count(batch, "subjects")
    chosen: list[str] = []
    total = 0
    for file, count in per_file.items():
        if not file.startswith("-") and total + count <= cap:
            chosen.append(file)
            total += count
    skipped = {file for file in per_file if file not in chosen}
    return Plan(tuple(chosen), subjects, total, len(skipped), sum(per_file[file] for file in skipped))


def _judgement(output: bytes, plan: Plan) -> Judgement | Prevented:
    try:
        report = json.loads(output)
        if report.get("errors"):
            return Prevented(f"{REVIEWER} reported errors while judging")
        findings = tuple(_finding(item) for item in report["findings"] if item.get("reported", True))
        spent = report.get("spent") or {}
        return Judgement(
            findings,
            plan.subjects,
            plan.skipped_files,
            plan.skipped_subjects,
            _count(spent, "calls"),
            _count(report, "cachedCount"),
        )
    except ValueError, KeyError, TypeError, AttributeError:
        return Prevented(f"{REVIEWER} printed a report that cannot be read")


def _finding(item: dict) -> Finding:
    message = item.get("message") or item.get("ask") or ""
    if not isinstance(item["rule"], str) or not isinstance(item["file"], str) or not isinstance(message, str):
        raise TypeError("finding fields must be strings")
    return Finding(
        item["rule"], item["file"], _count(item, "line"), message, _number(item.get("value")), _number(item.get("at"))
    )


def _count(mapping: dict, key: str) -> int:
    value = mapping.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None
