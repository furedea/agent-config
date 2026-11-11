"""Judge a session's changes with the model rules at Stop, and decide whether the agent must see the findings.

It follows the verification receipts: findings on inputs not judged before block once so the agent sees them; the same
inputs never block again, and anything that prevents a run is only a message. The Stop hook shares this decision with
the verification so that one rule, "unchanged inputs never trap the agent", covers both.
"""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import model_rules_credentials
import model_rules_report
import model_rules_run
import trusted_owners
from model_rules_outcome import Judgement, Prevented
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
    receipt = record.results().get(RECEIPT_KEY)
    if isinstance(receipt, dict) and receipt.get("input") == inputs and isinstance(receipt.get("summary"), str):
        return _reused(record, receipt, stop_hook_active)
    outcome = _judge(record, deadline)
    if isinstance(outcome, Prevented):
        return _prevented(outcome)
    if not outcome.findings:
        message = model_rules_report.describe_clean(outcome)
        _save(record, {"input": inputs, "outcome": CLEAN, "summary": message})
        return Advice(message)
    message = model_rules_report.describe(outcome)
    blocking = not stop_hook_active
    _save(record, {"input": inputs, "outcome": SHOWN if blocking else UNSHOWN, "summary": message})
    return Advice(message, blocking)


def _reused(record: SessionRecord, receipt: dict, stop_hook_active: bool) -> Advice:
    """Answer from a receipt for the same inputs; findings the agent has not seen yet still block, once."""
    summary = receipt["summary"]
    if receipt.get("outcome") == UNSHOWN and not stop_hook_active:
        _save(record, {**receipt, "outcome": SHOWN})
        return Advice(summary, blocking=True)
    if receipt.get("outcome") in {SHOWN, UNSHOWN}:
        return Advice(f"Model rules · findings unchanged; not rerun\n{summary}")
    return Advice("Model rules · reused · unchanged since the last review")


def _prevented(prevented: Prevented) -> Advice:
    return Advice(f"Model rules skipped · {prevented.reason}")


def _save(record: SessionRecord, receipt: dict) -> None:
    record.save_results({**record.results(), RECEIPT_KEY: receipt})


def _preconditions(record: SessionRecord) -> Prevented | None:
    """The cheap reasons not to run, checked before anything is read from the Keychain or sent anywhere."""
    if not RULES_DIRECTORY.is_dir():
        return Prevented("no model rules are installed with the hooks")
    if not record.baseline.changed_paths(capture(record.root)):
        return Prevented("no changes since session registration")
    return model_rules_run.is_installed() or _repository_gate(record.root)


def _judge(record: SessionRecord, deadline: model_rules_run.Deadline) -> Judgement | Prevented:
    if (stop := _preconditions(record)) is not None:
        return stop
    credentials = model_rules_credentials.load()
    if isinstance(credentials, Prevented):
        return credentials
    return model_rules_run.review_all(_reviews(record), credentials, deadline)


def _reviews(record: SessionRecord) -> tuple[model_rules_run.Review, ...]:
    """The commits made since the session started, then the changes not committed yet.

    `jev-lint review` judges `base...HEAD` or, without a base, the working tree against HEAD; neither covers both.
    """
    cache = model_rules_run.cache_path(state_directory())
    start = record.head
    reviews = []
    if start is not None and head_commit(record.root) != start:
        reviews.append(model_rules_run.Review(record.root, start, RULES_DIRECTORY, cache))
    if changed := _changed_files(record):
        reviews.append(model_rules_run.Review(record.root, None, RULES_DIRECTORY, cache, changed))
    return tuple(reviews)


def _changed_files(record: SessionRecord) -> tuple[str, ...]:
    """The existing files whose content differs from the session's baseline.

    The review of uncommitted changes is limited to these, so that edits and untracked files that were already there
    when the session started, and that it never touched, are not sent to the model.
    """
    changed = record.baseline.changed_paths(capture(record.root))
    return tuple(path for path in changed if not path.startswith("-") and (record.root / path).is_file())


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
