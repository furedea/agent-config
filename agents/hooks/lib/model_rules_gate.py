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
BUDGET_SECONDS = 90.0


@dataclass(frozen=True, slots=True)
class Advice:
    """What the Stop hook tells about the model rules, and whether the agent must see it as a block reason."""

    message: str
    blocking: bool = False


def advise(record: SessionRecord, *, stop_hook_active: bool, budget_seconds: float = BUDGET_SECONDS) -> Advice:
    """Run or reuse the model rules for the session's current inputs; never raises for an unusable setup."""
    try:
        return _advise(record, stop_hook_active, model_rules_run.Deadline.after(budget_seconds))
    except (OSError, ValueError, TypeError, KeyError) as error:
        return _prevented(Prevented(f"unexpected error: {error}"))


def _advise(record: SessionRecord, stop_hook_active: bool, deadline: model_rules_run.Deadline) -> Advice:
    state = record.results()
    inputs = _inputs(record)
    receipt = state.get(RECEIPT_KEY)
    if isinstance(receipt, dict) and receipt.get("input") == inputs and isinstance(receipt.get("summary"), str):
        return _reused(receipt)
    outcome = _judge(record, deadline)
    if isinstance(outcome, Prevented):
        return _prevented(outcome)
    if not outcome.findings:
        message = model_rules_report.describe_clean(outcome)
        _save(record, state, {"input": inputs, "outcome": "clean", "summary": message})
        return Advice(message)
    message = model_rules_report.describe(outcome)
    _save(record, state, {"input": inputs, "outcome": "findings", "summary": message})
    return Advice(message, blocking=not stop_hook_active)


def _reused(receipt: dict) -> Advice:
    if receipt.get("outcome") == "findings":
        return Advice(f"Model rules · findings unchanged; not rerun\n{receipt['summary']}")
    return Advice("Model rules · reused · unchanged since the last review")


def _prevented(prevented: Prevented) -> Advice:
    return Advice(f"Model rules skipped · {prevented.reason}")


def _save(record: SessionRecord, state: dict, receipt: dict) -> None:
    state[RECEIPT_KEY] = receipt
    record.save_results(state)


def _preconditions(record: SessionRecord) -> Prevented | None:
    """The cheap reasons not to run, checked before anything is read from the Keychain or sent anywhere."""
    if os.environ.get(KILL_SWITCH) == "off":
        return Prevented(f"{KILL_SWITCH}=off")
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
    committed = start is not None and head_commit(record.root) != start
    bases = (start, None) if committed else (None,)
    return tuple(model_rules_run.Review(record.root, base, RULES_DIRECTORY, cache) for base in bases)


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
