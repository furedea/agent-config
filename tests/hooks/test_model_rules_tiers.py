"""Rules with an eval baseline claim the Stop subject cap before the untuned rules do."""

import sys
from pathlib import Path
from typing import Any, cast

from tests.runtime import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import model_rules_gate
import model_rules_run
from model_rules_outcome import Judgement, Plan

REAL_RULES = REPO_ROOT / "agents/hooks/lint/model-rules"


def rule_folder(root: Path, language: str, name: str, *, baseline: bool) -> Path:
    folder = root / language / name
    folder.mkdir(parents=True)
    (folder / "rule.yml").write_text("id: x\n")
    if baseline:
        (folder / "baseline.json").write_text("{}")
    return folder


def test_tuned_rules_are_the_first_tier_and_the_rest_the_second(tmp_path: Path) -> None:
    tuned = rule_folder(tmp_path, "python", "fitted", baseline=True)
    untuned = rule_folder(tmp_path, "go", "new", baseline=False)

    assert model_rules_gate.rule_tiers(tmp_path) == ((tuned,), (untuned,))


def test_one_kind_of_rule_is_reviewed_through_the_whole_directory(tmp_path: Path) -> None:
    rule_folder(tmp_path, "python", "fitted", baseline=True)

    assert model_rules_gate.rule_tiers(tmp_path) == ((tmp_path,),)


def test_the_shipped_rules_put_the_tuned_naming_rule_before_the_migrated_ones() -> None:
    tuned, untuned = model_rules_gate.rule_tiers(REAL_RULES)

    assert REAL_RULES / "python/command-query-naming" in tuned
    assert REAL_RULES / "python/function-single-purpose" in untuned
    assert not set(tuned) & set(untuned)


def test_a_review_names_every_rule_folder_of_its_tier(tmp_path: Path) -> None:
    folders = (tmp_path / "a", tmp_path / "b")
    review = model_rules_run.Review(tmp_path, None, folders, tmp_path / "cache.json", cast(Any, None))

    assert review._rule_arguments() == ("-R", str(folders[0]), "-R", str(folders[1]))


class FakeReview:
    """A review that costs `cost` subjects and records the cap it was offered."""

    def __init__(self, cost: int, offered: list[int]) -> None:
        self.cost = cost
        self.offered = offered

    def plan(self, _deadline: object, cap: int) -> Plan:
        self.offered.append(cap)
        return Plan((), self.cost, min(self.cost, cap))

    def judge(self, plan: Plan, _credentials: object, _deadline: object) -> Judgement:
        return Judgement((), plan.subjects)


def test_the_cap_is_spent_on_the_first_review_before_the_next_is_offered_what_is_left() -> None:
    offered: list[int] = []
    reviews = (FakeReview(15, offered), FakeReview(15, offered))

    model_rules_run.review_all(cast(Any, reviews), cast(Any, None), cast(Any, None))

    assert offered == [model_rules_run.SUBJECT_CAP, model_rules_run.SUBJECT_CAP - 15]
