"""A later tier that fails keeps the earlier findings, is retried alone, and never re-blocks on what was shown."""

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from tests.runtime import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import model_rules_gate
import model_rules_report
import model_rules_resume
import model_rules_run
from model_rules_files import Selection
from model_rules_outcome import Finding, Judgement, Plan, Prevented, Resume

FINDING = Finding("command-query-naming", "a.py", 1, "m", 0.9, 0.5)
LATER = Finding("function-single-purpose", "b.py", 2, "m")


class Review:
    """A review of `paths` that costs `cost` subjects and returns `result` when judged."""

    def __init__(self, result: Judgement | Prevented, *, paths: tuple[str, ...] = ("a.py",), cost: int = 3) -> None:
        self.result = result
        self.paths = paths
        self.cost = cost
        self.offered: list[int] = []
        self.judged = False

    @property
    def scope(self) -> str:
        return repr(self.paths)

    def plan(self, _deadline: object, cap: int) -> Plan:
        self.offered.append(cap)
        return Plan((), self.cost, self.cost)

    def judge(self, _plan: Plan, _credentials: object, _deadline: object) -> Judgement | Prevented:
        self.judged = True
        return self.result


def run(reviews: tuple[Review, ...], resume: Resume | None = None) -> Judgement | Prevented:
    return model_rules_run.Reviews(cast(Any, reviews), resume).judge(cast(Any, None), cast(Any, None))


def test_a_failed_later_review_reports_why_and_how_many_files_it_skipped() -> None:
    reviews = (
        Review(Judgement((FINDING,), 3)),
        Review(Prevented("jev-lint timed out after 60s"), paths=("b.py", "c.py")),
    )

    outcome = run(reviews)

    assert isinstance(outcome, Judgement)
    assert outcome.failure_reason == "jev-lint timed out after 60s"
    assert outcome.skipped_files == 2


def test_a_failed_later_review_leaves_the_part_that_completed_to_resume_from() -> None:
    reviews = (Review(Judgement((FINDING,), 3)), Review(Prevented("x")))

    outcome = run(reviews)

    assert isinstance(outcome, Judgement)
    assert outcome.resume is not None
    assert outcome.resume.completed == 1
    assert outcome.resume.spent == 3
    assert outcome.resume.judgement.findings == (FINDING,)
    assert outcome.resume.judgement.failed_reviews == 0


def resume_after_failing(reviews: tuple[Review, ...]) -> Resume:
    """The resume that a run of reviews shaped like `reviews`, whose second review fails, leaves behind."""
    first, second = reviews[0].paths, reviews[1].paths
    outcome = run((Review(Judgement((FINDING,), 3), paths=first), Review(Prevented("x"), paths=second)))
    assert isinstance(outcome, Judgement)
    assert outcome.resume is not None
    return outcome.resume


def test_a_resumed_run_judges_only_the_reviews_that_did_not_complete() -> None:
    first, second = Review(Judgement((FINDING,), 3)), Review(Judgement((LATER,), 3))

    outcome = run((first, second), resume_after_failing((first, second)))

    assert isinstance(outcome, Judgement)
    assert not first.judged
    assert outcome.findings == (FINDING, LATER)
    assert second.offered == [model_rules_run.SUBJECT_CAP - 3]
    assert outcome.resume is None
    assert outcome.failed_reviews == 0


def test_a_resumed_run_that_fails_again_resumes_from_the_same_place() -> None:
    reviews = (Review(Judgement((FINDING,), 3)), Review(Prevented("again")))

    outcome = run(reviews, resume_after_failing(reviews))

    assert isinstance(outcome, Judgement)
    assert outcome.resume is not None
    assert outcome.resume.completed == 1
    assert outcome.findings == (FINDING,)


def test_a_resume_left_by_other_reviews_starts_the_run_over() -> None:
    """Moving commits after a failure (`git reset --soft`) regroups the same files into other reviews."""
    resume = resume_after_failing((Review(Judgement(())), Review(Judgement(()))))
    first, second = Review(Judgement((), 3), paths=("a.py", "b.py")), Review(Judgement((LATER,), 3))

    outcome = run((first, second), resume)

    assert isinstance(outcome, Judgement)
    assert first.judged
    assert first.offered == [model_rules_run.SUBJECT_CAP]
    assert outcome.findings == (LATER,)


def test_the_failure_reason_is_in_the_result_line() -> None:
    line = model_rules_report.describe_line(
        Judgement((), failed_reviews=1, failure_reason="jev-lint timed out after 60s")
    )

    assert "incomplete" in line
    assert "jev-lint timed out after 60s" in line
    assert "retried next Stop" in line


def test_a_resume_survives_the_receipt_file() -> None:
    resume = Resume(1, 3, Judgement((FINDING,), 3, 1, 2, 4, 5, usd=0.25), layout="reviews")

    assert model_rules_resume.load(model_rules_resume.dump(resume)) == resume


@pytest.mark.parametrize(
    "record",
    [
        None,
        "x",
        {},
        {"completed": "1", "spent": 3, "part": {}},
        {"completed": 1, "spent": 3, "part": {"findings": [1]}},
    ],
)
def test_a_malformed_resume_is_not_used(record: object) -> None:
    assert model_rules_resume.load(record) is None


def test_the_reviews_of_two_tiers_run_committed_then_uncommitted_within_each_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = tmp_path / "rules"
    for name, baseline in (("tuned", True), ("untuned", False)):
        folder = rules / "python" / name
        folder.mkdir(parents=True)
        (folder / "rule.yml").write_text("id: x\n")
        if baseline:
            (folder / "baseline.json").write_text("{}")
    monkeypatch.setattr(model_rules_gate, "RULES_DIRECTORY", rules)
    monkeypatch.setattr(model_rules_run, "cache_path", lambda _directory: tmp_path / "cache.json")
    changes = model_rules_gate._Changes(Selection(("c.py",)), Selection(("u.py",)), "abc")
    record = cast(Any, SimpleNamespace(root=tmp_path, head="abc"))

    reviews = changes.reviews(record, cast(Any, None))

    assert [(review.base, review.rules[0].name, review.paths) for review in reviews] == [
        ("abc", "tuned", ("c.py",)),
        (None, "tuned", ("u.py",)),
        ("abc", "untuned", ("c.py",)),
        (None, "untuned", ("u.py",)),
    ]


class Stops:
    """A record whose receipts persist across `advise` calls, and a `_judge` that returns the outcomes in turn."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *outcomes: Judgement | Prevented) -> None:
        self.saved: dict = {}
        self.resumes: list[Resume | None] = []
        self._outcomes = list(outcomes)
        self._record = SimpleNamespace(
            root=Path("/nonexistent"), results=lambda: self.saved, save_results=self.saved.update
        )
        monkeypatch.setattr(model_rules_gate, "_inputs", lambda _record: "same-inputs")
        monkeypatch.setattr(model_rules_gate, "_judge", self._judge)

    def _judge(self, _record: object, _deadline: object, resume: Resume | None = None) -> Judgement | Prevented:
        self.resumes.append(resume)
        return self._outcomes.pop(0)

    def stop(self, *, active: bool = False) -> model_rules_gate.Advice:
        return model_rules_gate._advise(cast(Any, self._record), active, cast(Any, None))


def partial(findings: tuple[Finding, ...]) -> Judgement:
    done = Judgement(findings, 3)
    return done.combined(Judgement((), failed_reviews=1, failure_reason="timed out", resume=Resume(1, 3, done)))


def test_findings_before_a_failed_tier_block_once_and_are_not_shown_again(monkeypatch: pytest.MonkeyPatch) -> None:
    stops = Stops(monkeypatch, partial((FINDING,)), partial((FINDING,)))

    first, second = stops.stop(), stops.stop()

    assert first.blocking
    assert not second.blocking


def test_the_stop_after_a_failed_tier_retries_from_what_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    stops = Stops(monkeypatch, partial((FINDING,)), Judgement((FINDING,), 6))

    stops.stop()
    stops.stop()

    assert stops.resumes[0] is None
    assert stops.resumes[1] == Resume(1, 3, Judgement((FINDING,), 3))


def test_a_retry_that_finds_more_blocks_for_the_new_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    stops = Stops(monkeypatch, partial((FINDING,)), Judgement((FINDING, LATER), 6))

    stops.stop()

    assert stops.stop().blocking


def test_a_completed_retry_saves_a_receipt_that_needs_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    stops = Stops(monkeypatch, partial((FINDING,)), Judgement((FINDING,), 6))

    stops.stop()
    stops.stop()

    assert "resume" not in stops.saved[model_rules_gate.RECEIPT_KEY]
    assert not stops.stop().blocking
    assert len(stops.resumes) == 2


def test_findings_withheld_by_an_active_stop_hook_block_at_the_next_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    stops = Stops(monkeypatch, partial((FINDING,)), Judgement((FINDING,), 6))

    assert not stops.stop(active=True).blocking
    assert stops.stop().blocking


def test_a_retry_that_cannot_run_keeps_the_receipt_for_the_next_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    stops = Stops(monkeypatch, partial((FINDING,)), Prevented("no time left"), Judgement((FINDING,), 6))

    stops.stop()
    stops.stop()

    stops.stop()

    assert stops.resumes[2] == Resume(1, 3, Judgement((FINDING,), 3))


def test_a_retry_that_finds_more_shows_only_the_findings_not_shown_before(monkeypatch: pytest.MonkeyPatch) -> None:
    stops = Stops(monkeypatch, partial((FINDING,)), Judgement((FINDING, LATER), 6))

    stops.stop()
    advice = stops.stop()

    assert "b.py:2" in advice.details
    assert "a.py:1" not in advice.details


def test_a_receipt_that_withholds_findings_keeps_only_the_unshown_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    stops = Stops(monkeypatch, partial((FINDING,)), Judgement((FINDING, LATER), 6))

    assert stops.stop().blocking
    assert not stops.stop(active=True).blocking
    receipt = stops.saved[model_rules_gate.RECEIPT_KEY]

    assert "b.py:2" in receipt["details"]
    assert "a.py:1" not in receipt["details"]
