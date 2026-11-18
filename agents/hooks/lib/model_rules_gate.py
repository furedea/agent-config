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
import model_rules_resume
import model_rules_run
import trusted_owners
from model_rules_files import ReviewedSpan, Selection, committed_paths, own_committed_paths, select, uncommitted_paths
from model_rules_outcome import Judgement, Prevented, Resume
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
# Rules named like this judge ADRs (docs/adr/), not every file of their language.
ADR_RULE_PREFIX = "adr-"


@dataclass(frozen=True, slots=True)
class Advice:
    """What the Stop hook tells about the model rules, and whether the agent must see it as a block reason."""

    message: str
    blocking: bool = False
    details: str = ""

    @property
    def reason(self) -> str:
        """The block reason: the result line, then the instruction and findings."""
        return f"{self.message}\n{self.details}" if self.details else self.message


def advise(record: SessionRecord, *, stop_hook_active: bool, budget_seconds: float = BUDGET_SECONDS) -> Advice:
    """Run or reuse the model rules for the session's current inputs; never raises for an unusable setup."""
    if os.environ.get(KILL_SWITCH) == "off":
        # First of all: a stored receipt must not make the rules speak after the user turned them off.
        return _skipped_advice(Prevented(f"{KILL_SWITCH}=off"))
    if budget_seconds <= 0:
        return _skipped_advice(Prevented("the Stop hook has no time left for the model rules"))
    try:
        return _advise(record, stop_hook_active, model_rules_run.Deadline.after(budget_seconds))
    except (OSError, ValueError, TypeError, KeyError) as error:
        return _skipped_advice(Prevented(f"unexpected error: {error}"))


def _advise(record: SessionRecord, stop_hook_active: bool, deadline: model_rules_run.Deadline) -> Advice:
    stop = _Stop(record, _inputs(record), stop_hook_active, deadline)
    receipt = record.results().get(RECEIPT_KEY)
    if not (
        isinstance(receipt, dict) and receipt.get("input") == stop.inputs and isinstance(receipt.get("findings"), int)
    ):
        return stop.judged()
    resume = model_rules_resume.load(receipt.get("resume"))
    if resume is None:
        advice = stop.answered_from(receipt)
        if advice.blocking:
            _save(record, {**receipt, "outcome": SHOWN})
        return advice
    return replace(stop, shown=_shown(receipt)).judged(resume)


@dataclass(frozen=True, slots=True)
class _Stop:
    """One Stop being advised: the session, the fingerprint of its inputs, and how many findings were shown before."""

    record: SessionRecord
    inputs: str
    stop_hook_active: bool
    deadline: model_rules_run.Deadline
    shown: int = 0

    def judged(self, resume: Resume | None = None) -> Advice:
        """Run the reviews, or only those a failed run left, and save what a later Stop on the same inputs reuses.

        A finding blocks once: those shown before a later review failed are not shown again, and a review that
        failed is retried alone at the next Stop.
        """
        started = time.monotonic()
        outcome = _judge(self.record, self.deadline, resume) if resume else _judge(self.record, self.deadline)
        if isinstance(outcome, Prevented):
            return _skipped_advice(outcome)
        outcome = replace(outcome, seconds=time.monotonic() - started)
        blocking = len(outcome.findings) > self.shown and not self.stop_hook_active
        seen = len(outcome.findings) if blocking else self.shown
        if not outcome.failed_reviews or outcome.resume:
            _save(self.record, self._receipt(outcome, seen))
        message = model_rules_report.describe_line(outcome)
        unseen = replace(outcome, findings=outcome.findings[self.shown :])
        return Advice(message, blocking, model_rules_report.describe_details(unseen) if blocking else "")

    def answered_from(self, receipt: dict) -> Advice:
        """The advice a complete receipt for the same inputs gives; findings not shown yet block, once."""
        return _answer_from(receipt, self.stop_hook_active)

    def _receipt(self, outcome: Judgement, seen: int) -> dict:
        """What a later Stop on the same inputs reuses, and the measurements that let the timing be studied.

        A run that a later review cut short also holds the `resume` from which only that review is retried.
        """
        state = CLEAN if not outcome.findings else SHOWN if seen == len(outcome.findings) else UNSHOWN
        resume = {"resume": model_rules_resume.dump(outcome.resume)} if outcome.resume else {}
        return {
            **resume,
            "input": self.inputs,
            "outcome": state,
            "shown": seen,
            "findings": len(outcome.findings),
            "details": model_rules_report.describe_details(replace(outcome, findings=outcome.findings[seen:])),
            "subjects": outcome.subjects,
            "judged": outcome.judged,
            "requests": outcome.requests,
            "cached": outcome.cached,
            "seconds": round(outcome.seconds, 3),
            "usd": outcome.usd,
        }


def _shown(receipt: dict) -> int:
    """How many of a receipt's findings the agent has been shown."""
    shown = receipt.get("shown")
    if isinstance(shown, int) and not isinstance(shown, bool):
        return shown
    return receipt["findings"] if receipt.get("outcome") == SHOWN else 0


def _answer_from(receipt: dict, stop_hook_active: bool) -> Advice:
    """The advice a receipt for the same inputs gives; findings the agent has not seen yet block, once."""
    message = model_rules_report.describe_unchanged(receipt["findings"])
    if receipt.get("outcome") == UNSHOWN and not stop_hook_active:
        return Advice(message, blocking=True, details=str(receipt.get("details", "")))
    return Advice(message)


def _skipped_advice(prevented: Prevented) -> Advice:
    return Advice(model_rules_report.describe_skipped(prevented.reason))


def _save(record: SessionRecord, receipt: dict) -> None:
    record.save_results({**record.results(), RECEIPT_KEY: receipt})


def _preconditions(record: SessionRecord) -> Prevented | None:
    """The cheap reasons not to run, checked before anything is read from the Keychain or sent anywhere."""
    if not RULES_DIRECTORY.is_dir():
        return Prevented("no model rules are installed with the hooks")
    if not record.baseline.changed_paths(capture(record.root)):
        return Prevented("no changes since session registration")
    return _repository_gate(record.root)


def _judge(
    record: SessionRecord, deadline: model_rules_run.Deadline, resume: Resume | None = None
) -> Judgement | Prevented:
    if (stop := _preconditions(record)) is not None:
        return stop
    programs = model_rules_programs.locate()
    if isinstance(programs, Prevented):
        return programs
    changes = _Changes.of(record)
    reviews = changes.reviews(record, programs)
    withheld = Judgement((), withheld_files=len(changes.withheld))
    if not reviews:
        return withheld
    credentials = model_rules_credentials.load()
    if isinstance(credentials, Prevented):
        return credentials
    outcome = model_rules_run.Reviews(reviews, resume).judge(credentials, deadline)
    return outcome if isinstance(outcome, Prevented) else outcome.combined(withheld)


@dataclass(frozen=True, slots=True)
class _Changes:
    """The files a session changed that may be sent, in the commits it made and in the working tree."""

    committed: Selection
    uncommitted: Selection

    @classmethod
    def of(cls, record: SessionRecord) -> _Changes:
        """Select among the commits made since the session started and the files that differ from its baseline.

        Files that were already there when the session started and that it never touched are not sent, nor are files
        that a fast-forward or pull brought in and that the session has not edited since. When HEAD's reflog cannot say
        which commits are the session's, every commit since the session started is judged.
        """
        return cls(_committed_selection(record), _uncommitted_selection(record))

    @property
    def withheld(self) -> frozenset[str]:
        """Every withheld path once, however many reviews it would have been part of."""
        return self.committed.withheld | self.uncommitted.withheld

    def reviews(self, record: SessionRecord, programs: Programs) -> tuple[model_rules_run.Review, ...]:
        """For each tier of rules, the commits made since the session started, then the changes not committed yet.

        `jev-lint review` judges `base...HEAD` or, without a base, the working tree against HEAD; neither covers both.
        The tuned tier comes first so that it takes the subject cap before the untuned rules do. The ADR rules come
        last and see only the ADRs whose body is new or changed, so they never judge other Markdown.
        """
        cache = model_rules_run.cache_path(state_directory())
        reviews = []
        for rules in rule_tiers(RULES_DIRECTORY):
            if self.committed.sendable:
                reviews.append(
                    model_rules_run.Review(record.root, record.head, rules, cache, programs, self.committed.sendable)
                )
            if self.uncommitted.sendable:
                reviews.append(
                    model_rules_run.Review(record.root, None, rules, cache, programs, self.uncommitted.sendable)
                )
        adr_folders = adr_rules(RULES_DIRECTORY)
        if adr_folders and self.committed.adrs:
            reviews.append(
                model_rules_run.Review(record.root, record.head, adr_folders, cache, programs, self.committed.adrs)
            )
        if adr_folders and self.uncommitted.adrs:
            reviews.append(
                model_rules_run.Review(record.root, None, adr_folders, cache, programs, self.uncommitted.adrs)
            )
        return tuple(reviews)


def rule_tiers(directory: Path) -> tuple[tuple[Path, ...], ...]:
    """The rules to review with, in the order they claim the subject cap: rules with an eval baseline, then the rest.

    A file that does not fit the cap is skipped whole, so rules that were never fitted must not displace the tuned
    ones. The ADR rules are not part of any tier: `adr_rules` reviews them apart. When every other rule is of one
    kind there is one tier: the whole directory, or its non-ADR folders when ADR rules sit beside them.
    """
    adr_folders = set(adr_rules(directory))
    folders = sorted(path.parent for path in directory.glob("*/*/rule.yml") if path.parent not in adr_folders)
    tuned = tuple(folder for folder in folders if (folder / "baseline.json").is_file())
    untuned = tuple(folder for folder in folders if folder not in tuned)
    if tuned and untuned:
        return (tuned, untuned)
    if adr_folders:
        return (tuple(folders),) if folders else ()
    return ((directory,),)


def adr_rules(directory: Path) -> tuple[Path, ...]:
    """The rule folders that judge ADRs, which must only ever be given ADR files."""
    return tuple(sorted(path.parent for path in directory.glob(f"*/{ADR_RULE_PREFIX}*/rule.yml")))


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


def _committed_selection(record: SessionRecord) -> Selection:
    if record.head is None:
        return Selection()
    return select(record.root, _session_commits_paths(record, record.head), ReviewedSpan(record.head, "HEAD"))


def _session_commits_paths(record: SessionRecord, head: str) -> tuple[str, ...]:
    if head_commit(record.root) == head:
        return ()
    try:
        return own_committed_paths(record.root, head, record.reflog)
    except ValueError:
        return committed_paths(record.root, head)


def _uncommitted_selection(record: SessionRecord) -> Selection:
    changed = record.baseline.changed_paths(capture(record.root))
    if record.head is not None:
        # Without a starting commit there was nothing to fast-forward over, so every changed file is the session's.
        dirty = uncommitted_paths(record.root)
        changed = tuple(path for path in changed if path in dirty)
    return select(record.root, changed, ReviewedSpan("HEAD"))


def _inputs(record: SessionRecord) -> str:
    """A fingerprint of everything a review depends on: the files, the base commit, and the rules."""
    digest = hashlib.sha256(capture(record.root).digest.encode())
    digest.update((record.head or "").encode())
    # The same files can be the session's or not depending on how HEAD got there, which the snapshot cannot tell.
    try:
        digest.update("\0".join(_session_commits_paths(record, record.head) if record.head else ()).encode())
        digest.update(b"\1" + "\0".join(sorted(uncommitted_paths(record.root))).encode())
    except ValueError:
        digest.update(b"reflog unavailable")
    for path in sorted(RULES_DIRECTORY.rglob("*.yml")):
        digest.update(os.fsencode(path.relative_to(RULES_DIRECTORY)))
        digest.update(path.read_bytes())
    # A baseline moves a rule between tiers, so its presence changes what the cap leaves for it.
    for path in sorted(RULES_DIRECTORY.rglob("baseline.json")):
        digest.update(os.fsencode(path.relative_to(RULES_DIRECTORY)))
    return digest.hexdigest()
