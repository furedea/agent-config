"""adr-check rejects every departure from the ADR-0025 front-matter shape and every broken reference."""

import subprocess
import textwrap
from pathlib import Path

import pytest
from tests.runtime import REPO_ROOT

BODY = "\n# Title\n\n## Context and Problem Statement\n\nText.\n"


def adr(front_matter: str, body: str = BODY) -> str:
    return f"---\n{textwrap.dedent(front_matter).strip()}\n---\n{body}"


def accepted(extra: str = "") -> str:
    return adr(f"status: accepted\ndate: 2026-01-01\n{extra}")


def run(directory: Path, *options: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["adr-check", *options, str(directory)], capture_output=True, text=True, check=False)


def write_all(directory: Path, files: dict[str, str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (directory / name).write_text(text)
    return directory


def findings(tmp_path: Path, files: dict[str, str]) -> str:
    result = run(write_all(tmp_path / "adr", files))
    assert result.returncode == 1, result.stdout + result.stderr
    return result.stdout


def test_conforming_directory_passes(tmp_path: Path) -> None:
    directory = write_all(
        tmp_path / "adr",
        {
            "0001_first.md": adr(
                """
                status: superseded
                date: 2026-01-01
                superseded-by: [ADR-0002]
                amended:
                  - "2026-02-01: clarified the scope"
                decision-makers: [alice, bob]
                """
            ),
            "0002_second.md": accepted("supersedes: [ADR-0001]\nrelated: [other-repo/ADR-0099]  # a comment"),
            "0003_third.md": accepted("partly-superseded-by: [ADR-0004]"),
            "0004_fourth.md": accepted("supersedes: [ADR-0003]"),
        },
    )
    result = run(directory)
    assert (result.returncode, result.stdout) == (0, "")


def test_this_repositorys_adrs_pass() -> None:
    result = run(REPO_ROOT / "docs" / "adr")
    assert (result.returncode, result.stdout) == (0, "")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("# Title\n\nText.\n", "front matter is missing"),
        ("---\nstatus: accepted\n# Title\n", "front matter is missing"),
        (accepted("owner: alice"), "owner"),
        (adr("status: maybe\ndate: 2026-01-01"), "status"),
        (adr("status: accepted\ndate: 01/01/2026"), "date"),
        (adr("status: accepted\ndate: 2026-02-30"), "date"),
        (adr("status: accepted"), "'date' is a required property"),
        (accepted("related:"), "related"),
        (accepted("related: ADR-0002"), "related"),
        (accepted('related: ["see ADR-0002"]'), "related"),
        (accepted("related: [ADR-2]"), "related"),
        (accepted('amended: ["clarified"]'), "amended"),
        (accepted("amended: [2026-02-01]"), "amended"),
        (adr("status: superseded\ndate: 2026-01-01"), "superseded-by"),
        (accepted("superseded-by: [ADR-0002]"), "superseded-by"),
        (adr("status: accepted\nstatus: proposed\ndate: 2026-01-01"), "not valid YAML"),
        (adr("status: [accepted\ndate: 2026-01-01"), "not valid YAML"),
        ("---\n- accepted\n---\n# Title\n", "front matter"),
    ],
)
def test_front_matter_outside_the_schema_is_a_violation(tmp_path: Path, text: str, expected: str) -> None:
    output = findings(tmp_path, {"0001_a.md": text})
    assert "0001_a.md" in output
    assert expected in output


def test_file_name_without_an_id_is_a_violation(tmp_path: Path) -> None:
    assert "NNNN_words.md" in findings(tmp_path, {"decision.md": accepted()})


def test_duplicate_id_is_reported_for_both_files(tmp_path: Path) -> None:
    output = findings(tmp_path, {"0001_a.md": accepted(), "0001_b.md": accepted()})
    assert "0001_a.md: ID ADR-0001 is also used by 0001_b.md" in output
    assert "0001_b.md: ID ADR-0001 is also used by 0001_a.md" in output


def test_unprefixed_reference_to_a_missing_adr_is_a_violation(tmp_path: Path) -> None:
    assert "ADR-0099, which does not exist" in findings(tmp_path, {"0001_a.md": accepted("related: [ADR-0099]")})


def test_prefixed_reference_is_not_resolved(tmp_path: Path) -> None:
    result = run(write_all(tmp_path / "adr", {"0001_a.md": accepted("related: [elsewhere/ADR-0099]")}))
    assert result.returncode == 0


def test_supersedes_needs_the_target_to_name_the_successor(tmp_path: Path) -> None:
    output = findings(tmp_path, {"0001_a.md": accepted(), "0002_b.md": accepted("supersedes: [ADR-0001]")})
    assert "0002_b.md: supersedes ADR-0001" in output


def test_superseded_by_needs_the_successor_to_list_supersedes(tmp_path: Path) -> None:
    old = adr("status: superseded\ndate: 2026-01-01\nsuperseded-by: [ADR-0002]")
    output = findings(tmp_path, {"0001_a.md": old, "0002_b.md": accepted()})
    assert "0001_a.md: names ADR-0002 as its successor" in output


def test_partly_superseded_by_needs_the_successor_to_list_supersedes(tmp_path: Path) -> None:
    output = findings(tmp_path, {"0001_a.md": accepted("partly-superseded-by: [ADR-0002]"), "0002_b.md": accepted()})
    assert "0001_a.md: names ADR-0002 as its successor" in output


def test_all_findings_are_reported_in_one_run(tmp_path: Path) -> None:
    output = findings(
        tmp_path, {"0001_a.md": accepted("owner: x"), "0002_b.md": adr("status: maybe\ndate: 2026-01-01")}
    )
    assert "0001_a.md" in output
    assert "0002_b.md" in output


def test_missing_directory_is_a_usage_error(tmp_path: Path) -> None:
    result = run(tmp_path / "absent")
    assert result.returncode == 2
    assert "not a directory" in result.stderr


class Repository:
    """A git repository whose docs/adr directory changes after a base commit."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.directory = root / "docs" / "adr"
        self.directory.mkdir(parents=True)
        self.git("init", "--quiet", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *arguments], capture_output=True, text=True, check=True
        ).stdout.strip()

    def commit(self, files: dict[str, str]) -> str:
        write_all(self.directory, files)
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "change")
        return self.git("rev-parse", "HEAD")

    def check_since(self, base: str) -> subprocess.CompletedProcess[str]:
        return run(self.directory, "--base", base)


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    return Repository(tmp_path / "repo")


def test_front_matter_of_an_accepted_adr_may_change_after_the_base(repository: Repository) -> None:
    base = repository.commit({"0001_a.md": accepted(), "0002_b.md": accepted()})
    repository.commit({"0001_a.md": adr("status: superseded\ndate: 2026-01-01\nsuperseded-by: [ADR-0002]")})
    repository.commit({"0002_b.md": accepted("supersedes: [ADR-0001]")})
    assert repository.check_since(base).returncode == 0


def test_new_adrs_and_unaccepted_ones_may_change_freely(repository: Repository) -> None:
    base = repository.commit({"0001_a.md": adr("status: proposed\ndate: 2026-01-01")})
    repository.commit({"0001_a.md": adr("status: proposed\ndate: 2026-01-01", "\n# Other\n"), "0002_b.md": accepted()})
    assert repository.check_since(base).returncode == 0


def test_body_change_of_an_accepted_adr_is_a_violation(repository: Repository) -> None:
    base = repository.commit({"0001_a.md": accepted()})
    repository.commit({"0001_a.md": accepted().replace("Text.", "Other text.")})
    result = repository.check_since(base)
    assert result.returncode == 1
    assert "0001_a.md: accepted at" in result.stdout
    assert "body changed" in result.stdout


def test_removal_of_an_accepted_adr_is_a_violation(repository: Repository) -> None:
    base = repository.commit({"0001_a.md": accepted()})
    (repository.directory / "0001_a.md").unlink()
    result = repository.check_since(base)
    assert result.returncode == 1
    assert "removed or renumbered" in result.stdout


def test_renumbering_an_accepted_adr_is_a_violation(repository: Repository) -> None:
    base = repository.commit({"0001_a.md": accepted()})
    (repository.directory / "0001_a.md").rename(repository.directory / "0007_a.md")
    result = repository.check_since(base)
    assert result.returncode == 1
    assert "0001_a.md: accepted at" in result.stdout


def test_unknown_base_is_a_usage_error(repository: Repository) -> None:
    repository.commit({"0001_a.md": accepted()})
    result = repository.check_since("no-such-revision")
    assert result.returncode == 2
    assert "cannot read ADRs at the base commit" in result.stderr


def test_base_without_the_directory_has_nothing_to_protect(repository: Repository) -> None:
    repository.git("commit", "--quiet", "--allow-empty", "-m", "empty")
    base = repository.git("rev-parse", "HEAD")
    repository.commit({"0001_a.md": accepted()})
    assert repository.check_since(base).returncode == 0


def test_unreadable_front_matter_of_an_accepted_adr_is_not_reported_as_removed(repository: Repository) -> None:
    base = repository.commit({"0001_a.md": accepted()})
    repository.commit({"0001_a.md": adr("status: [accepted\ndate: 2026-01-01")})
    result = repository.check_since(base)
    assert "not valid YAML" in result.stdout
    assert "removed or renumbered" not in result.stdout
