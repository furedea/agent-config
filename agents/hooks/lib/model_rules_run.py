"""Run `jev-lint review` over a session's changes, within a cap, a lock and a deadline.

The process boundary is the only place that touches the model: `jev-lint` is started directly and `op` injects its key,
so the hook handles only the service-account token, and only in the environment of the `op` child. Both programs
are started by the trusted absolute paths of `model_rules_programs`, with a PATH that holds nothing else.
"""

import json
import os
import signal
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import model_rules_programs
from model_rules_credentials import Credentials
from model_rules_outcome import Finding, Judgement, Plan, Prevented
from model_rules_programs import Programs
from session_store import LockTimeoutError, StateError, file_lock, private_directory

REVIEWER = "jev-lint"
SUBJECT_CAP = 20
PLAN_TIMEOUT_SECONDS = 20.0
JUDGE_TIMEOUT_SECONDS = 60.0
LOCK_TIMEOUT_SECONDS = 30.0
OUTPUT_LIMIT_BYTES = 8 * 1024 * 1024
# Nothing else is passed on: TYPESAFE_BASE_URL or JEV_LINT_CACHE would redirect the code or the cache.
ENVIRONMENT_ALLOWLIST = ("HOME", "USER", "LANG", "LC_ALL", "XDG_STATE_HOME", "TMPDIR")
# Set by us, never inherited: git must read every path handed to `jev-lint` as a file name, not as a pathspec pattern.
FIXED_ENVIRONMENT = {"GIT_LITERAL_PATHSPECS": "1"}
TOKEN_VARIABLE = "OP_SERVICE_ACCOUNT_TOKEN"
TIMEOUT_PROGRAM = "/usr/bin/timeout"
DEADLINE_SIGNAL = "TERM"
KILL_AFTER_SECONDS = 5
# How `timeout` reports a command that ran past its limit: 124; 137 (GNU) after it had to send KILL; and, as BSD
# `timeout` is itself in the process group it kills, the signal that ended it as a negative status.
DEADLINE_STATUSES = (124, 137, -signal.SIGKILL)


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
    `paths` limits a review to those files; a review that applies the cap names its own subset instead. `programs`
    are the trusted `op` and `jev-lint` it starts.
    """

    root: Path
    base: str | None
    rules: tuple[Path, ...]
    cache: Path
    programs: Programs
    paths: tuple[str, ...] = ()

    def plan(self, deadline: Deadline, cap: int) -> Plan | Prevented:
        """Count the subjects without asking the model, and keep the files whose subjects fit `cap`."""
        report = self._dry_run(deadline, self.paths)
        if isinstance(report, Prevented):
            return report
        try:
            return _capped_plan(report, cap)
        except ValueError, KeyError, TypeError, AttributeError:
            return Prevented(f"{REVIEWER} printed a plan that cannot be read")

    def judge(self, plan: Plan, credentials: Credentials, deadline: Deadline) -> Judgement | Prevented:
        """Ask the model about the planned subjects, with the verdict cache shared by every session.

        The cached count is planned under the same lock, just before the model is asked, so it is the state the
        judgement uses: neither the plan of the whole diff nor another session's later writes can make it differ.
        """
        try:
            private_directory(self.cache.parent)
            with file_lock(self.cache.parent / ".lock", timeout=max(0.0, deadline.remaining(LOCK_TIMEOUT_SECONDS))):
                return self._judge_locked(plan, credentials, deadline)
        except LockTimeoutError:
            return Prevented("another session holds the verdict cache lock")
        except (OSError, StateError) as error:
            return Prevented(f"the verdict cache directory is unusable: {error}")

    def _judge_locked(self, plan: Plan, credentials: Credentials, deadline: Deadline) -> Judgement | Prevented:
        paths = plan.paths or self.paths
        cached = self._cached_count(deadline, paths)
        if isinstance(cached, Prevented):
            return cached
        arguments = (
            str(self.programs.launcher),
            "run",
            "--environment",
            credentials.environment,
            "--",
            str(self.programs.reviewer),
            *self._arguments(),
            *paths,
        )
        child = _Child(arguments, _environment({TOKEN_VARIABLE: credentials.token}), self.root)
        output = child.run(deadline.remaining(JUDGE_TIMEOUT_SECONDS))
        if isinstance(output, Prevented):
            return output
        return _judgement(output, plan, cached)

    def _cached_count(self, deadline: Deadline, paths: tuple[str, ...]) -> int | Prevented:
        report = self._dry_run(deadline, paths)
        if isinstance(report, Prevented):
            return report
        try:
            return _count(report, "cached")
        except TypeError:
            return Prevented(f"{REVIEWER} printed a plan that cannot be read")

    def _dry_run(self, deadline: Deadline, paths: tuple[str, ...]) -> dict | Prevented:
        arguments = (str(self.programs.reviewer), *self._arguments("--dry-run"), *paths)
        output = _Child(arguments, _environment(), self.root).run(deadline.remaining(PLAN_TIMEOUT_SECONDS))
        if isinstance(output, Prevented):
            return output
        try:
            report = json.loads(output)
        except ValueError:
            return Prevented(f"{REVIEWER} printed a plan that cannot be read")
        if not isinstance(report, dict):
            return Prevented(f"{REVIEWER} printed a plan that cannot be read")
        return report

    def _rule_arguments(self) -> tuple[str, ...]:
        return tuple(word for path in self.rules for word in ("-R", str(path)))

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
            *self._rule_arguments(),
            "-c",
            str(self.cache),
        )


def review_all(reviews: tuple[Review, ...], credentials: Credentials, deadline: Deadline) -> Judgement | Prevented:
    """Judge each review in turn, sharing one cap of SUBJECT_CAP subjects among them."""
    combined = Judgement(())
    cap = SUBJECT_CAP
    for position, review in enumerate(reviews):
        plan = review.plan(deadline, cap)
        if isinstance(plan, Prevented):
            return _failed_review(plan, position, combined)
        outcome = review.judge(plan, credentials, deadline) if plan.judged else _unjudged(plan)
        if isinstance(outcome, Prevented):
            return _failed_review(outcome, position, combined)
        cap = max(0, cap - plan.cost)
        combined = combined.combined(outcome)
    return combined


def _failed_review(prevented: Prevented, position: int, combined: Judgement) -> Judgement | Prevented:
    """The first review failing prevents the run; a later one keeps the earlier findings and is retried next Stop."""
    return prevented if position == 0 else combined.combined(Judgement((), skipped_files=1, failed_reviews=1))


def cache_path(state_directory: Path) -> Path:
    """Where the shared verdict cache lives: under the agent state directory, outside every repository."""
    return state_directory.parent / "model-rules" / "verdicts.json"


def _environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The allowlisted variables and a PATH of trusted directories only, never the caller's PATH."""
    allowed = {name: os.environ[name] for name in ENVIRONMENT_ALLOWLIST if name in os.environ}
    return {**allowed, **FIXED_ENVIRONMENT, "PATH": model_rules_programs.search_path(), **(extra or {})}


@dataclass(frozen=True, slots=True)
class _Child:
    """A process to run to the end: its argv, its whole environment, and where it runs."""

    arguments: tuple[str, ...]
    environment: dict[str, str]
    cwd: Path

    def run(self, timeout: float) -> bytes | Prevented:
        """Run it to the deadline; stderr is discarded and never surfaced.

        Two things end it. `timeout(1)` runs beside the hook and still fires if Claude Code kills the hook, which
        macOS cannot signal to a child. The hook's own process-group kill backs it up, a little later, and is all
        there is when `/usr/bin/timeout` does not exist.
        """
        program = Path(self.arguments[0]).name
        if timeout <= 0:
            return Prevented("the Stop hook has no time left for the model rules")
        wrapper = _deadline_wrapper(timeout)
        try:
            process = subprocess.Popen(
                (*wrapper, *self.arguments),
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
            output, _ = process.communicate(timeout=timeout + (KILL_AFTER_SECONDS + 1 if wrapper else 0))
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            output = None
        if output is None or (wrapper and process.returncode in DEADLINE_STATUSES):
            return Prevented(f"{program} timed out after {timeout:.0f}s")
        if process.returncode != 0:
            return Prevented(f"{program} exited with status {process.returncode}")
        if len(output) > OUTPUT_LIMIT_BYTES:
            return Prevented(f"{program} printed more than {OUTPUT_LIMIT_BYTES // (1024 * 1024)} MiB")
        return output


def _deadline_wrapper(timeout: float) -> tuple[str, ...]:
    """The `timeout` words that bound a child to `timeout` seconds, or () when there is no `timeout` to use.

    It is the system's, named by absolute path so that nothing on PATH can stand in for it: macOS ships a BSD one and
    Linux a GNU one at the same place. Only what both take is used: short options and a plain number of seconds.
    """
    if not os.access(TIMEOUT_PROGRAM, os.X_OK):
        return ()
    # Under a millisecond rounds to "0.000", which `timeout` reads as no limit at all.
    return (TIMEOUT_PROGRAM, "-s", DEADLINE_SIGNAL, "-k", str(KILL_AFTER_SECONDS), f"{max(timeout, 0.001):.3f}")


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


def _judgement(output: bytes, plan: Plan, cached: int) -> Judgement | Prevented:
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
            cached,
            usd=_number(spent.get("usd")) or 0.0,
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
