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
from dataclasses import dataclass, replace
from pathlib import Path

import model_rules_programs
from model_rules_credentials import Credentials
from model_rules_outcome import Finding, Judgement, Plan, Prevented, Resumable
from model_rules_programs import Programs
from session_store import LockTimeoutError, StateError, file_lock, private_directory

REVIEWER = "jev-lint"
COMMITTED, UNCOMMITTED = "committed", "uncommitted"
SUBJECT_CAP = 20
PLAN_TIMEOUT_SECONDS = 20.0
JUDGE_TIMEOUT_SECONDS = 60.0
LOCK_TIMEOUT_SECONDS = 30.0
OUTPUT_LIMIT_BYTES = 8 * 1024 * 1024
# Nothing else is passed on: TYPESAFE_BASE_URL or JEV_LINT_CACHE would redirect the code or the cache.
ENVIRONMENT_ALLOWLIST = ("HOME", "USER", "LANG", "LC_ALL", "XDG_STATE_HOME", "TMPDIR")
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
    `paths` limits a review to those files; a review that applies the cap names its own subset instead. `pending`
    names the files an earlier run of the same inputs skipped. `programs` are the trusted `op` and `jev-lint` it
    starts.
    """

    root: Path
    base: str | None
    rules: Path
    cache: Path
    programs: Programs
    paths: tuple[str, ...] = ()
    pending: frozenset[str] = frozenset()

    def plan(self, deadline: Deadline, cap: int) -> Plan | Prevented:
        """Count the subjects without asking the model, and keep the files whose subjects fit `cap`.

        When the review has `pending` files, the other files were judged by an earlier run and sit in the verdict
        cache, so they are passed again at no cost and only the `pending` files compete for `cap`.
        """
        arguments = (str(self.programs.reviewer), *self._arguments("--dry-run"), *self.paths)
        child = _Child(arguments, _environment(), self.root)
        output = child.run(deadline.remaining(PLAN_TIMEOUT_SECONDS))
        if isinstance(output, Prevented):
            return output
        try:
            return _capped_plan(json.loads(output), cap, self.pending)
        except ValueError, KeyError, TypeError, AttributeError:
            return Prevented(f"{REVIEWER} printed a plan that cannot be read")

    def judge(self, plan: Plan, credentials: Credentials, deadline: Deadline) -> Judgement | Prevented:
        """Ask the model about the planned subjects, with the verdict cache shared by every session."""
        try:
            private_directory(self.cache.parent)
            with file_lock(self.cache.parent / ".lock", timeout=max(0.0, deadline.remaining(LOCK_TIMEOUT_SECONDS))):
                arguments = (
                    str(self.programs.launcher),
                    "run",
                    "--environment",
                    credentials.environment,
                    "--",
                    str(self.programs.reviewer),
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

    @property
    def kind(self) -> str:
        """Which of the two reviews of a session this is: the commits since `base`, or the uncommitted changes."""
        return COMMITTED if self.base else UNCOMMITTED

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
        resumable = tuple(Resumable(review.kind, file) for file in plan.resumable)
        combined = combined.combined(replace(outcome, resumable=resumable))
    return combined


def cache_path(state_directory: Path) -> Path:
    """Where the shared verdict cache lives: under the agent state directory, outside every repository."""
    return state_directory.parent / "model-rules" / "verdicts.json"


def _environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The allowlisted variables and a PATH of trusted directories only, never the caller's PATH."""
    allowed = {name: os.environ[name] for name in ENVIRONMENT_ALLOWLIST if name in os.environ}
    return {**allowed, "PATH": model_rules_programs.search_path(), **(extra or {})}


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


def _capped_plan(report: dict, cap: int, pending: frozenset[str]) -> Plan:
    subjects, cached = _count(report, "subjects"), _count(report, "cached")
    if subjects - cached <= cap:
        return Plan((), subjects, subjects - cached)
    per_file: dict[str, int] = {}
    for batch in report["batches"]:
        per_file[batch["file"]] = per_file.get(batch["file"], 0) + _count(batch, "subjects")
    pending = frozenset(file for file in pending if file in per_file)
    chosen = _judged_before(per_file, pending, subjects - cached)
    total = 0
    for file, count in per_file.items():
        if (not pending or file in pending) and _passable(file) and total + count <= cap:
            chosen.append(file)
            total += count
    skipped = [file for file in per_file if file not in chosen]
    # A file over the whole cap would be skipped on every run, so naming it would make each Stop resume for nothing.
    resumable = tuple(file for file in skipped if _admissible(file, per_file[file]))
    return Plan(tuple(chosen), subjects, total, len(skipped), sum(per_file[file] for file in skipped), resumable)


def _judged_before(per_file: dict[str, int], pending: frozenset[str], uncached: int) -> list[str]:
    """The files an earlier run of the same inputs judged, for the verdict cache to answer at no cost.

    The report does not say which subjects are cached. Files that were never judged are the pending ones and those
    over the whole cap, so any uncached subject beyond theirs means the cache no longer answers for the rest. Then
    none are sent: the pending files compete for the cap alone, and the cost stays within it.
    """
    if not pending:
        return []
    never_judged = sum(count for file, count in per_file.items() if file in pending or not _admissible(file, count))
    if uncached > never_judged:
        return []
    return [file for file, count in per_file.items() if file not in pending and _admissible(file, count)]


def _admissible(file: str, subjects: int) -> bool:
    """Whether the cap can ever admit the file: it is not an option-like path and its subjects fit the whole cap."""
    return _passable(file) and subjects <= SUBJECT_CAP


def _passable(file: str) -> bool:
    """Whether the file can be given to `jev-lint` as a path argument; one that starts with `-` would be an option."""
    return not file.startswith("-")


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
