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
import model_rules_seen
import trusted_owners
from model_rules_files import ReviewedSpan, Selection, committed_paths, review_base, select
from model_rules_outcome import Judgement, Prevented, Resume
from model_rules_programs import Programs
from session_snapshot import capture, head_commit
from session_store import SessionRecord, state_directory

HOOK_ROOT = Path(__file__).resolve().parent.parent
RULES_DIRECTORY = HOOK_ROOT / "lint" / "model-rules"
TRUSTED_OWNERS_FILE = HOOK_ROOT / "rules" / "trusted_owners.json"
KILL_SWITCH = "AGENT_MODEL_RULES"
RECEIPT_KEY = "model_rules"
# The fingerprints of the findings the agent was shown in this session, kept beside the receipt in the session results.
SHOWN_KEY = "model_rules_shown"
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
            _remember(record, receipt.get("keys"))
            _save(record, {**receipt, "outcome": SHOWN})
        return advice
    return stop.judged(resume)


@dataclass(frozen=True, slots=True)
class _Stop:
    """One Stop being advised: the session and the fingerprint of its inputs."""

    record: SessionRecord
    inputs: str
    stop_hook_active: bool
    deadline: model_rules_run.Deadline

    def judged(self, resume: Resume | None = None) -> Advice:
        """Run the reviews, or only those a failed run left, and save what a later Stop on the same inputs reuses.

        A finding blocks once per session: one shown before, by this Stop or an earlier one, is only counted, and a
        review that failed is retried alone at the next Stop.
        """
        started = time.monotonic()
        outcome = _judge(self.record, self.deadline, resume) if resume else _judge(self.record, self.deadline)
        if isinstance(outcome, Prevented):
            return _skipped_advice(outcome)
        outcome = replace(outcome, seconds=time.monotonic() - started)
        known = _remembered(self.record)
        keys = {model_rules_seen.fingerprint(self.record.root, item): item for item in outcome.findings}
        fresh = replace(outcome, findings=tuple(item for key, item in keys.items() if key not in known))
        blocking = bool(fresh.findings) and not self.stop_hook_active
        if blocking:
            _remember(self.record, [*keys.keys() - known])
        if not outcome.failed_reviews or outcome.resume:
            _save(self.record, self._receipt(fresh, [*keys.keys() - known], blocking))
        message = model_rules_report.describe_line(fresh, len(outcome.findings) - len(fresh.findings))
        return Advice(message, blocking, model_rules_report.describe_details(fresh) if blocking else "")

    def answered_from(self, receipt: dict) -> Advice:
        """The advice a complete receipt for the same inputs gives; findings not shown yet block, once."""
        return _answer_from(receipt, self.stop_hook_active)

    def _receipt(self, outcome: Judgement, keys: list[str], blocking: bool) -> dict:
        """What a later Stop on the same inputs reuses, and the measurements that let the timing be studied.

        A run that a later review cut short also holds the `resume` from which only that review is retried.
        """
        state = CLEAN if not outcome.findings else SHOWN if blocking else UNSHOWN
        resume = {"resume": model_rules_resume.dump(outcome.resume)} if outcome.resume else {}
        return {
            **resume,
            "input": self.inputs,
            "outcome": state,
            "keys": keys,
            "findings": len(outcome.findings),
            "details": model_rules_report.describe_details(outcome),
            "subjects": outcome.subjects,
            "judged": outcome.judged,
            "requests": outcome.requests,
            "cached": outcome.cached,
            "seconds": round(outcome.seconds, 3),
            "usd": outcome.usd,
        }


def _answer_from(receipt: dict, stop_hook_active: bool) -> Advice:
    """The advice a receipt for the same inputs gives; findings the agent has not seen yet block, once."""
    message = model_rules_report.describe_unchanged(receipt["findings"])
    if receipt.get("outcome") == UNSHOWN and not stop_hook_active:
        return Advice(message, blocking=True, details=str(receipt.get("details", "")))
    return Advice(message)


def _skipped_advice(prevented: Prevented) -> Advice:
    return Advice(model_rules_report.describe_skipped(prevented.reason))


def _remembered(record: SessionRecord) -> set[str]:
    keys = record.results().get(SHOWN_KEY)
    return {key for key in keys if isinstance(key, str)} if isinstance(keys, list) else set()


def _remember(record: SessionRecord, keys: object) -> None:
    if isinstance(keys, list):
        record.save_results({**record.results(), SHOWN_KEY: sorted(_remembered(record) | {*keys})})


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
    base: str | None = None

    @classmethod
    def of(cls, record: SessionRecord) -> _Changes:
        """Select among the commits made since the session started and the files that differ from its baseline.

        Files that were already there when the session started and that it never touched are not sent.
        """
        base = review_base(record.root, record.head) if record.head is not None else None
        committed = Selection()
        if base is not None and head_commit(record.root) != base:
            committed = select(record.root, committed_paths(record.root, base), ReviewedSpan(base, "HEAD"))
        changed = record.baseline.changed_paths(capture(record.root))
        return cls(committed, select(record.root, changed, ReviewedSpan("HEAD")), base)

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
                    model_rules_run.Review(record.root, self.base, rules, cache, programs, self.committed.sendable)
                )
            if self.uncommitted.sendable:
                reviews.append(
                    model_rules_run.Review(record.root, None, rules, cache, programs, self.uncommitted.sendable)
                )
        adr_folders = adr_rules(RULES_DIRECTORY)
        if adr_folders and self.committed.adrs:
            reviews.append(
                model_rules_run.Review(record.root, self.base, adr_folders, cache, programs, self.committed.adrs)
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


def _inputs(record: SessionRecord) -> str:
    """A fingerprint of everything a review depends on: the files, the commit the review starts from, and the rules."""
    digest = hashlib.sha256(capture(record.root).digest.encode())
    digest.update((review_base(record.root, record.head) if record.head else "").encode())
    for path in sorted(RULES_DIRECTORY.rglob("*.yml")):
        digest.update(os.fsencode(path.relative_to(RULES_DIRECTORY)))
        digest.update(path.read_bytes())
    # A baseline moves a rule between tiers, so its presence changes what the cap leaves for it.
    for path in sorted(RULES_DIRECTORY.rglob("baseline.json")):
        digest.update(os.fsencode(path.relative_to(RULES_DIRECTORY)))
    return digest.hexdigest()
