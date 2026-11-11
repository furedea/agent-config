"""Judge a session's changes with the model rules at Stop, and decide whether the agent must see the findings.

It follows the verification receipts: findings on inputs not judged before block once so the agent sees them; the same
inputs never block again, and anything that prevents a run is only a message. The Stop hook shares this decision with
the verification so that one rule, "unchanged inputs never trap the agent", covers both.
"""

import hashlib
import os
import time
from dataclasses import dataclass, replace
from pathlib import Path

import model_rules_credentials
import model_rules_programs
import model_rules_report
import model_rules_run
import trusted_owners
from model_rules_files import Selection, committed_paths, select
from model_rules_outcome import Finding, Judgement, Prevented, Resumable
from model_rules_programs import Programs
from session_snapshot import capture, head_commit
from session_store import SessionRecord, state_directory

HOOK_ROOT = Path(__file__).resolve().parent.parent
RULES_DIRECTORY = HOOK_ROOT / "lint" / "model-rules"
TRUSTED_OWNERS_FILE = HOOK_ROOT / "rules" / "trusted_owners.json"
KILL_SWITCH = "AGENT_MODEL_RULES"
RECEIPT_KEY = "model_rules"
# Receipt outcomes: no findings; findings the agent has been shown by a block; findings it has not been shown yet
# because `stop_hook_active` kept them from blocking, which block once at the next Stop on the same inputs.
CLEAN, SHOWN, UNSHOWN = "clean", "findings", "findings-unshown"
BUDGET_SECONDS = 90.0


@dataclass(frozen=True, slots=True)
class Advice:
    """What the Stop hook tells about the model rules, and whether the agent must see it as a block reason."""

    message: str
    blocking: bool = False


def advise(record: SessionRecord, *, stop_hook_active: bool, budget_seconds: float = BUDGET_SECONDS) -> Advice:
    """Run or reuse the model rules for the session's current inputs; never raises for an unusable setup."""
    if os.environ.get(KILL_SWITCH) == "off":
        # First of all: a stored receipt must not make the rules speak after the user turned them off.
        return _prevented(Prevented(f"{KILL_SWITCH}=off"))
    if budget_seconds <= 0:
        return _prevented(Prevented("the Stop hook has no time left for the model rules"))
    try:
        return _advise(record, stop_hook_active, model_rules_run.Deadline.after(budget_seconds))
    except (OSError, ValueError, TypeError, KeyError) as error:
        return _prevented(Prevented(f"unexpected error: {error}"))


def _advise(record: SessionRecord, stop_hook_active: bool, deadline: model_rules_run.Deadline) -> Advice:
    inputs = _inputs(record)
    stored = record.results().get(RECEIPT_KEY)
    known = isinstance(stored, dict) and stored.get("input") == inputs and isinstance(stored.get("summary"), str)
    return _Stop(record, inputs, stop_hook_active, stored if known else None).advise(deadline)


@dataclass(frozen=True, slots=True)
class _Stop:
    """One Stop's decision about the model rules, given the receipt of an earlier Stop on the same inputs, if any.

    A receipt whose last run skipped files because of the cap is not final: the next Stop on the same inputs judges
    the skipped files, and only a receipt that skipped nothing is reused.
    """

    record: SessionRecord
    inputs: str
    stop_hook_active: bool
    receipt: dict | None

    def advise(self, deadline: model_rules_run.Deadline) -> Advice:
        """Reuse a final receipt, otherwise judge, resuming from what an unfinished receipt skipped."""
        if self.receipt is not None and not self.receipt.get("resumable"):
            return self._reused(self.receipt)
        started = time.monotonic()
        outcome = _judge(self.record, deadline, self._pending())
        if isinstance(outcome, Prevented):
            return self._unfinished(outcome)
        return self._conclude(replace(outcome, seconds=time.monotonic() - started))

    def _conclude(self, outcome: Judgement) -> Advice:
        if not outcome.findings:
            message = model_rules_report.describe_clean(outcome)
            self._save(CLEAN, message, outcome)
            return Advice(message)
        message = model_rules_report.describe(outcome)
        fresh = bool({_key(finding) for finding in outcome.findings} - self._shown())
        blocking = fresh and not self.stop_hook_active
        # Findings the agent already saw only notify; new ones that could not block yet wait for the next Stop.
        self._save(UNSHOWN if fresh and not blocking else SHOWN, message, outcome)
        return Advice(message, blocking)

    def _reused(self, receipt: dict) -> Advice:
        """Answer from a receipt for the same inputs; findings the agent has not seen yet still block, once."""
        summary = receipt["summary"]
        if receipt.get("outcome") == UNSHOWN and not self.stop_hook_active:
            shown = sorted(_keys(receipt, "shown") | _keys(receipt, "found"))
            self.record.save_results(
                {**self.record.results(), RECEIPT_KEY: {**receipt, "outcome": SHOWN, "shown": shown}}
            )
            return Advice(summary, blocking=True)
        if receipt.get("outcome") in {SHOWN, UNSHOWN}:
            return Advice(f"Model rules · findings unchanged; not rerun\n{summary}")
        return Advice("Model rules · reused · unchanged since the last review")

    def _unfinished(self, prevented: Prevented) -> Advice:
        """A resume that could not run: say why, and still answer from the receipt so unseen findings are not lost."""
        if self.receipt is None:
            return _prevented(prevented)
        reused = self._reused(self.receipt)
        return Advice(f"{_prevented(prevented).message}\n{reused.message}", reused.blocking)

    def _pending(self) -> frozenset[Resumable]:
        if self.receipt is None:
            return frozenset()
        return frozenset(Resumable(review, file) for review, file in self.receipt.get("resumable", ()))

    def _shown(self) -> frozenset[tuple[str, str, int]]:
        """The findings an earlier Stop on these inputs has put in front of the agent."""
        return _keys(self.receipt, "shown") if self.receipt is not None else frozenset()

    def _save(self, outcome: str, summary: str, judgement: Judgement) -> None:
        """Keep the receipt; `shown` grows by this run's findings only when the agent is shown them.

        `found` keeps the keys of the findings in `summary`, so a receipt that was not shown yet can become shown
        later without running again.
        """
        found = {_key(finding) for finding in judgement.findings}
        shown = self._shown() | (found if outcome == SHOWN else set())
        receipt = {
            "input": self.inputs,
            "outcome": outcome,
            "summary": summary,
            "resumable": [[item.review, item.file] for item in judgement.resumable],
            "found": sorted(found),
            "shown": sorted(shown),
        }
        self.record.save_results({**self.record.results(), RECEIPT_KEY: receipt})


def _key(finding: Finding) -> tuple[str, str, int]:
    return finding.rule, finding.file, finding.line


def _keys(receipt: dict, field: str) -> frozenset[tuple[str, str, int]]:
    return frozenset((rule, file, line) for rule, file, line in receipt.get(field, ()))


def _prevented(prevented: Prevented) -> Advice:
    return Advice(f"Model rules skipped · {prevented.reason}")


def _preconditions(record: SessionRecord) -> Prevented | None:
    """The cheap reasons not to run, checked before anything is read from the Keychain or sent anywhere."""
    if not RULES_DIRECTORY.is_dir():
        return Prevented("no model rules are installed with the hooks")
    if not record.baseline.changed_paths(capture(record.root)):
        return Prevented("no changes since session registration")
    return _repository_gate(record.root)


def _judge(
    record: SessionRecord, deadline: model_rules_run.Deadline, pending: frozenset[Resumable]
) -> Judgement | Prevented:
    if (stop := _preconditions(record)) is not None:
        return stop
    programs = model_rules_programs.locate()
    if isinstance(programs, Prevented):
        return programs
    changes = _Changes.of(record)
    reviews = changes.reviews(record, programs, pending)
    withheld = Judgement((), withheld_files=len(changes.withheld))
    if not reviews:
        return withheld
    credentials = model_rules_credentials.load()
    if isinstance(credentials, Prevented):
        return credentials
    outcome = model_rules_run.review_all(reviews, credentials, deadline)
    return outcome if isinstance(outcome, Prevented) else outcome.combined(withheld)


@dataclass(frozen=True, slots=True)
class _Changes:
    """The files a session changed that may be sent, in the commits it made and in the working tree."""

    committed: Selection
    uncommitted: Selection

    @classmethod
    def of(cls, record: SessionRecord) -> _Changes:
        """Select among the commits made since the session started and the files that differ from its baseline.

        Files that were already there when the session started and that it never touched are not sent.
        """
        committed = Selection()
        if record.head is not None and head_commit(record.root) != record.head:
            committed = select(record.root, committed_paths(record.root, record.head))
        changed = record.baseline.changed_paths(capture(record.root))
        return cls(committed, select(record.root, changed))

    @property
    def withheld(self) -> frozenset[str]:
        """Every withheld path once, however many reviews it would have been part of."""
        return self.committed.withheld | self.uncommitted.withheld

    def reviews(
        self, record: SessionRecord, programs: Programs, pending: frozenset[Resumable]
    ) -> tuple[model_rules_run.Review, ...]:
        """The commits made since the session started, then the changes not committed yet.

        `jev-lint review` judges `base...HEAD` or, without a base, the working tree against HEAD; neither covers both.
        Each review gets only the files of `pending` that an earlier Stop on the same inputs skipped in that review.
        """
        cache = model_rules_run.cache_path(state_directory())
        reviews = []
        if self.committed.sendable:
            skipped = _skipped_in(pending, model_rules_run.COMMITTED)
            reviews.append(
                model_rules_run.Review(
                    record.root, record.head, RULES_DIRECTORY, cache, programs, self.committed.sendable, skipped
                )
            )
        if self.uncommitted.sendable:
            skipped = _skipped_in(pending, model_rules_run.UNCOMMITTED)
            reviews.append(
                model_rules_run.Review(
                    record.root, None, RULES_DIRECTORY, cache, programs, self.uncommitted.sendable, skipped
                )
            )
        return tuple(reviews)


def _skipped_in(pending: frozenset[Resumable], review: str) -> frozenset[str]:
    return frozenset(item.file for item in pending if item.review == review)


def _repository_gate(root: Path) -> Prevented | None:
    """Send code to the model only for repositories of trusted owners."""
    configured = Path(os.environ.get("AGENT_TRUSTED_OWNERS", str(TRUSTED_OWNERS_FILE)))
    try:
        distrust = trusted_owners.distrust_reason(root, trusted_owners.load(configured))
    except ValueError:
        return Prevented("the trusted owners file cannot be read, so no code is sent")
    if distrust is None:
        return None
    return Prevented(f"not sending code of a repository that is not trusted ({distrust.reason})")


def _inputs(record: SessionRecord) -> str:
    """A fingerprint of everything a review depends on: the files, the base commit, and the rules."""
    digest = hashlib.sha256(capture(record.root).digest.encode())
    digest.update((record.head or "").encode())
    for path in sorted(RULES_DIRECTORY.rglob("*.yml")):
        digest.update(os.fsencode(path.relative_to(RULES_DIRECTORY)))
        digest.update(path.read_bytes())
    return digest.hexdigest()
