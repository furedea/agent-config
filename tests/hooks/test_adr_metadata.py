"""ADR file names and metadata are checked after an edit under `docs/adr/` and reported, never blocked."""

import io
import json
from pathlib import Path

import pytest
from tests.runtime import REPO_ROOT, load_script_module

lint_format = load_script_module("agents/hooks/lint_format.py", "lint_format_for_adr_metadata")
adr_metadata = lint_format.adr_metadata

VALID = "# ADR-{id}: Pick a thing\n\n- Status: {status}\n- Date: 2026-01-01\n{extra}\nIn the context of x.\n"


def write_adr(
    directory: Path, name: str, status: str = "Accepted", extra: str = "", identifier: str | None = None
) -> Path:
    identifier = identifier or name[:4]
    path = directory / name
    path.write_text(VALID.format(id=identifier, status=status, extra=extra))
    return path


@pytest.fixture
def adr_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "docs" / "adr"
    directory.mkdir(parents=True)
    write_adr(directory, "0001_first_decision.md")
    write_adr(directory, "0002_second_decision.md")
    return directory


def messages(directory: Path) -> str:
    return "\n".join(adr_metadata.diagnostics(sorted(directory.glob("*.md"))))


def test_conforming_directory_is_silent(adr_directory: Path) -> None:
    assert messages(adr_directory) == ""


@pytest.mark.parametrize("name", ["1_short.md", "adr_three.md", "00031_long.md", "third.md"])
def test_file_name_must_start_with_a_four_digit_id(adr_directory: Path, name: str) -> None:
    write_adr(adr_directory, name, identifier="0003")
    assert "File name must start with a four-digit ID" in messages(adr_directory)


@pytest.mark.parametrize("name", ["0003-dashes.md", "0003_Upper.md", "0003.md", "0003 spaced name.md"])
def test_any_naming_style_after_the_id_is_accepted(adr_directory: Path, name: str) -> None:
    write_adr(adr_directory, name, identifier="0003")
    assert messages(adr_directory) == ""


def test_duplicate_id_is_reported_for_both_files(adr_directory: Path) -> None:
    write_adr(adr_directory, "0002_other_decision.md")
    assert messages(adr_directory).count("ID 0002 is used by more than one ADR") == 2


def test_title_must_have_the_adr_form(adr_directory: Path) -> None:
    (adr_directory / "0003_third_decision.md").write_text("# Third decision\n\n- Status: Accepted\n")
    assert "Title line must be `# ADR-NNNN: <title>`" in messages(adr_directory)


def test_title_id_must_match_file_name(adr_directory: Path) -> None:
    write_adr(adr_directory, "0003_third_decision.md", identifier="0009")
    assert "Title ID ADR-0009 does not match the file name ID 0003" in messages(adr_directory)


def test_status_is_required(adr_directory: Path) -> None:
    (adr_directory / "0003_third_decision.md").write_text("# ADR-0003: Third\n\n- Date: 2026-01-01\n")
    assert "Exactly one `- Status:` is required; found 0" in messages(adr_directory)


@pytest.mark.parametrize("status", ["Draft", "accepted", "Superseded by ADR-0001", ""])
def test_status_must_be_one_of_the_four_values(adr_directory: Path, status: str) -> None:
    write_adr(adr_directory, "0003_third_decision.md", status=status)
    assert "Status must be one of Proposed, Accepted, Superseded, Deprecated" in messages(adr_directory)


@pytest.mark.parametrize("status", ["Proposed", "Accepted", "Superseded", "Deprecated"])
def test_each_status_value_is_accepted(adr_directory: Path, status: str) -> None:
    write_adr(adr_directory, "0003_third_decision.md", status=status)
    assert messages(adr_directory) == ""


def test_official_metadata_vocabulary_is_accepted(adr_directory: Path) -> None:
    extra = (
        "- Partly superseded by: ADR-0003\n- Amended: 2026-02-01 (the hook behaviour)\n- Amended: 2026-02-02 (more)\n"
    )
    write_adr(adr_directory, "0001_first_decision.md", extra=extra)
    write_adr(adr_directory, "0003_third_decision.md")
    assert messages(adr_directory) == ""


def test_amended_needs_a_date_and_a_reason(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", extra="- Amended: sometime\n")
    assert "Amended must be `<YYYY-MM-DD> (<what>)`" in messages(adr_directory)


def test_unknown_metadata_key_is_reported(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", extra="- Owner: someone\n")
    assert "Unknown metadata key `Owner`" in messages(adr_directory)


def test_reference_to_a_missing_adr_is_reported(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", extra="- Partly superseded by: ADR-0042\n")
    assert "Partly superseded by names ADR-0042, which does not exist" in messages(adr_directory)


def test_reference_in_link_form_is_checked(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", extra="- Related: [ADR-0042](0042_x.md) (why)\n")
    assert "Related names ADR-0042" in messages(adr_directory)


def test_other_repository_references_are_not_checked(adr_directory: Path) -> None:
    extra = (
        "- Originally: furedea/dotfiles ADR-0031\n"
        "- Supersedes: [dotfiles ADR-0016](https://example.test/docs/adr/0016_x.md),\n"
        "  [dotfiles ADR-0030](https://example.test/docs/adr/0030_y.md)\n"
    )
    write_adr(adr_directory, "0003_third_decision.md", extra=extra)
    assert messages(adr_directory) == ""


def test_supersedes_requires_the_old_adr_to_be_superseded(adr_directory: Path) -> None:
    write_adr(adr_directory, "0003_third_decision.md", extra="- Supersedes: ADR-0001\n")
    assert "ADR-0001 is superseded here, so its Status must be `Superseded`" in messages(adr_directory)


def test_supersession_with_a_superseded_old_adr_passes(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", status="Superseded", extra="- Superseded by: ADR-0003\n")
    write_adr(adr_directory, "0003_third_decision.md", extra="- Supersedes: ADR-0001\n")
    assert messages(adr_directory) == ""


def test_multi_line_entry_continues_on_indented_lines(adr_directory: Path) -> None:
    write_adr(adr_directory, "0003_third_decision.md", extra="- Supersedes: ADR-0001,\n  ADR-0042\n")
    assert "Supersedes names ADR-0042" in messages(adr_directory)


def test_gaps_in_ids_are_not_reported_because_parallel_branches_reserve_numbers(adr_directory: Path) -> None:
    write_adr(adr_directory, "0004_fourth_decision.md")
    write_adr(adr_directory, "0006_sixth_decision.md")
    assert messages(adr_directory) == ""


def test_readme_and_non_adr_directories_are_ignored(adr_directory: Path, tmp_path: Path) -> None:
    (adr_directory / "README.md").write_text("# Decisions\n")
    other = tmp_path / "notes"
    other.mkdir()
    (other / "bad name.md").write_text("no title\n")
    assert adr_metadata.diagnostics([adr_directory / "README.md", other / "bad name.md"]) == ()
    assert messages(adr_directory) == ""


def test_reference_after_a_joining_word_is_checked(adr_directory: Path) -> None:
    write_adr(adr_directory, "0003_third_decision.md", extra="- Refines: ADR-0001 and ADR-0042\n")
    assert "Refines names ADR-0042" in messages(adr_directory)


def test_violations_of_adrs_the_edit_did_not_touch_are_not_reported(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", status="Draft")
    assert adr_metadata.diagnostics([adr_directory / "0002_second_decision.md"]) == ()


def test_supersession_is_reported_when_either_side_is_edited(adr_directory: Path) -> None:
    write_adr(adr_directory, "0003_third_decision.md", extra="- Supersedes: ADR-0001\n")
    assert adr_metadata.diagnostics([adr_directory / "0001_first_decision.md"]) != ()


def test_duplicate_id_is_reported_when_either_file_is_edited(adr_directory: Path) -> None:
    other = write_adr(adr_directory, "0002_other_decision.md")
    assert adr_metadata.diagnostics([other]) != ()


def test_metadata_key_with_a_hyphen_is_checked(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", extra="- Owner-ID: team\n")
    assert "Unknown metadata key `Owner-ID`" in messages(adr_directory)


def test_exactly_one_status_is_required(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", extra="- Status: Superseded\n")
    assert "Exactly one `- Status:` is required; found 2" in messages(adr_directory)


def test_deleting_an_adr_reports_references_that_now_dangle(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", extra="- Related: ADR-0003\n")
    deleted = adr_directory / "0003_third_decision.md"
    assert "Related names ADR-0003" in "\n".join(adr_metadata.diagnostics([deleted]))


def test_superseded_by_requires_superseded_status(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", extra="- Superseded by: ADR-0002\n")
    assert "Superseded by ADR-0002 requires `- Status: Superseded`" in messages(adr_directory)


def test_deleting_the_readme_is_not_an_adr_deletion(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", status="Draft")
    assert adr_metadata.diagnostics([adr_directory / "README.md"]) == ()


@pytest.mark.parametrize("value", ["", "later decision", "ADR-42"])
def test_relation_entry_must_name_an_adr(adr_directory: Path, value: str) -> None:
    write_adr(adr_directory, "0001_first_decision.md", extra=f"- Superseded by: {value}\n")
    assert "Superseded by must name at least one `ADR-NNNN`" in messages(adr_directory)


def test_relation_to_the_adr_itself_is_reported(adr_directory: Path) -> None:
    write_adr(adr_directory, "0001_first_decision.md", status="Superseded", extra="- Supersedes: ADR-0001\n")
    assert "Supersedes names ADR-0001, the ADR itself" in messages(adr_directory)


def test_reference_must_end_at_a_token_boundary(adr_directory: Path) -> None:
    write_adr(adr_directory, "0002_second_decision.md", extra="- Related: ADR-0001draft\n")
    assert "Related must name at least one `ADR-NNNN`" in messages(adr_directory)


def test_id_digits_must_be_ascii(adr_directory: Path) -> None:
    wide = "\uff11\uff12\uff13\uff14"
    (adr_directory / f"{wide}_wide.md").write_text(f"# ADR-{wide}: Wide\n\n- Status: Accepted\n")
    assert "File name must start with a four-digit ID" in messages(adr_directory)


def test_link_targets_are_not_scanned_for_references(adr_directory: Path) -> None:
    extra = "- Supersedes: [dotfiles ADR-0016](https://example.test/docs/ADR-0016.md)\n"
    write_adr(adr_directory, "0003_third_decision.md", extra=extra)
    assert messages(adr_directory) == ""


def test_this_repositorys_adr_history_conforms() -> None:
    directory = REPO_ROOT / "docs" / "adr"
    assert adr_metadata.diagnostics(sorted(directory.glob("*.md"))) == ()


def test_edit_hook_reports_adr_violations_as_context_and_exits_zero(
    adr_directory: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(lint_format, "check_file", lambda _kind, _path: ())
    monkeypatch.setattr(lint_format.static_rule_scan, "diagnostics", lambda _paths: ())
    path = write_adr(adr_directory, "0003_third_decision.md", status="Draft")
    payload = {"tool_name": "Write", "cwd": str(adr_directory), "tool_input": {"file_path": str(path)}}
    monkeypatch.setattr(lint_format.sys, "stdin", io.StringIO(json.dumps(payload)))
    status = lint_format.main([])
    context = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert status == 0
    assert f"ADR metadata · {path}:3" in context
