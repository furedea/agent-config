"""ADR rules are judged only on ADRs under docs/adr/ whose body is new or changed, never on other Markdown."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from tests.runtime import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import model_rules_files
import model_rules_gate
from model_rules_files import Selection

ADR = "docs/adr/0001_use_x.md"
FRONT_MATTER = "---\nstatus: proposed\ndate: 2026-11-01\n---\n"
BODY = "# Use X\n\nChosen option: X, because Y.\n"


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


def write(root: Path, path: str, text: str) -> None:
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text)


def commit_all(root: Path) -> str:
    git(root, "add", "-A")
    git(root, "commit", "--quiet", "-m", "step")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


@pytest.fixture
def root(git_project: Path) -> Path:
    write(git_project, ADR, FRONT_MATTER + BODY)
    write(git_project, "docs/notes.md", "# Notes\n")
    commit_all(git_project)
    return git_project


def adrs(root: Path, *paths: str) -> tuple[str, ...]:
    return model_rules_files.select(root, paths, "HEAD").adrs


def test_a_new_adr_is_selected(root: Path) -> None:
    write(root, "docs/adr/0002_use_z.md", FRONT_MATTER + BODY)

    assert adrs(root, "docs/adr/0002_use_z.md") == ("docs/adr/0002_use_z.md",)


def test_an_adr_whose_body_changed_is_selected(root: Path) -> None:
    write(root, ADR, FRONT_MATTER + BODY + "\nMore reasons.\n")

    assert adrs(root, ADR) == (ADR,)


def test_an_adr_whose_front_matter_only_changed_is_not_selected(root: Path) -> None:
    write(root, ADR, "---\nstatus: accepted\ndate: 2026-11-02\namended:\n  - 'later'\n---\n" + BODY)

    assert adrs(root, ADR) == ()


def test_an_unchanged_adr_is_not_selected(root: Path) -> None:
    assert adrs(root, ADR) == ()


def test_other_markdown_is_never_an_adr(root: Path) -> None:
    write(root, "docs/notes.md", "# Notes\n\nchanged\n")
    write(root, "README.md", "# New\n")
    write(root, "docs/adr/README.md", "# Index\n")
    write(root, "docs/adr/sub/0003_nested.md", FRONT_MATTER + BODY)

    assert adrs(root, "docs/notes.md", "README.md", "docs/adr/README.md", "docs/adr/sub/0003_nested.md") == ()


def test_a_body_change_is_measured_against_the_given_revision(root: Path) -> None:
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    write(root, ADR, FRONT_MATTER + BODY + "\nMore.\n")
    commit_all(root)

    assert model_rules_files.select(root, [ADR], base).adrs == (ADR,)
    assert model_rules_files.select(root, [ADR], "HEAD").adrs == ()


def test_an_adr_without_front_matter_counts_whole_text_as_body(root: Path) -> None:
    write(root, "docs/adr/0004_plain.md", BODY)
    commit_all(root)
    write(root, "docs/adr/0004_plain.md", BODY + "\nEdit.\n")

    assert adrs(root, "docs/adr/0004_plain.md") == ("docs/adr/0004_plain.md",)


def test_an_adr_stays_among_the_sendable_files_and_a_symlinked_adr_is_withheld(root: Path) -> None:
    write(root, ADR, FRONT_MATTER + BODY + "\nMore.\n")
    (root / "docs/adr/0005_link.md").symlink_to("0001_use_x.md")

    selection = model_rules_files.select(root, [ADR, "docs/adr/0005_link.md"], "HEAD")

    assert selection.sendable == (ADR,)
    assert selection.adrs == (ADR,)
    assert selection.withheld == {"docs/adr/0005_link.md"}


def test_the_adr_rules_are_not_part_of_the_general_tiers(tmp_path: Path) -> None:
    for language, name in (("python", "naming"), ("markdown", "adr-states-why")):
        folder = tmp_path / language / name
        folder.mkdir(parents=True)
        (folder / "rule.yml").write_text("id: x\n")

    assert model_rules_gate.rule_tiers(tmp_path) == ((tmp_path / "python/naming",),)
    assert model_rules_gate.adr_rules(tmp_path) == (tmp_path / "markdown/adr-states-why",)


def test_the_shipped_adr_rules_are_the_only_ones_reviewed_apart() -> None:
    folders = {path.name for path in model_rules_gate.adr_rules(model_rules_gate.RULES_DIRECTORY)}

    assert folders == {"adr-states-why", "adr-options-are-real-alternatives"}
    assert not any(
        "markdown" in path.parts
        for tier in model_rules_gate.rule_tiers(model_rules_gate.RULES_DIRECTORY)
        for path in tier
    )


def test_adr_rules_review_only_the_selected_adrs_after_the_general_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = tmp_path / "rules"
    for language, name in (("python", "naming"), ("markdown", "adr-states-why")):
        (rules / language / name).mkdir(parents=True)
        (rules / language / name / "rule.yml").write_text("id: x\n")
    monkeypatch.setattr(model_rules_gate, "RULES_DIRECTORY", rules)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    changes = model_rules_gate._Changes(Selection(("a.py", ADR), adrs=(ADR,)), Selection(("b.py", "docs/notes.md")))
    record = SimpleNamespace(root=tmp_path, head="abc")

    reviews = changes.reviews(cast(Any, record), cast(Any, None))

    assert [(review.base, review.paths, review.rules) for review in reviews] == [
        ("abc", ("a.py", ADR), (rules / "python/naming",)),
        (None, ("b.py", "docs/notes.md"), (rules / "python/naming",)),
        ("abc", (ADR,), (rules / "markdown/adr-states-why",)),
    ]
