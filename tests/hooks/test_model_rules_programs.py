"""Which `op` and `jev-lint` the Stop-time model rules start: only trusted ones, never one found through PATH.

`op` receives the 1Password service-account token, so a program that merely stands earlier on PATH must never be
started in its place.
"""

import os
import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import Tools
from tests.hooks.model_rules_support import edit, install_fakes, register_session, stop
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import model_rules_programs
import session_store
from model_rules_outcome import Prevented


@pytest.fixture(autouse=True)
def tools(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tools:
    return install_fakes(executable, tmp_path, monkeypatch)


@pytest.fixture
def programs(tmp_path: Path) -> Path:
    """The one trusted directory of these tests; `install_fakes` made it the stand-in for the Nix store."""
    return tmp_path / "bin"


@pytest.fixture
def record(git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> session_store.SessionRecord:
    registered = register_session(git_project, tmp_path, monkeypatch)
    edit(registered, "after\n")
    return registered


def plant(directory: Path, name: str, marker: Path) -> Path:
    """A program that records that it ran, standing in a directory the hook must not trust."""
    directory.mkdir(exist_ok=True)
    program = directory / name
    program.write_text(f"#!{sys.executable} -I\nimport pathlib\npathlib.Path({str(marker)!r}).write_text('ran')\n")
    program.chmod(0o700)
    return program


@pytest.mark.parametrize("name", ["op", "jev-lint"])
def test_a_program_planted_earlier_on_path_is_never_started(
    record: session_store.SessionRecord,
    tools: Tools,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    marker = tmp_path / "planted.marker"
    planted = tmp_path / "writable-project-bin"
    plant(planted, name, marker)
    monkeypatch.setenv("PATH", os.pathsep.join([str(planted), os.environ["PATH"]]))

    result = stop(record)

    assert not marker.exists()
    assert result["decision"] == "block"
    assert [call["argv"][0] for call in tools.calls("op")] == ["run"]


def test_the_programs_are_started_by_absolute_path_and_children_get_only_trusted_directories_on_path(
    record: session_store.SessionRecord, tools: Tools, programs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", os.pathsep.join(["/tmp/writable", os.environ["PATH"]]))

    stop(record)

    [wrapped] = [call for call in tools.calls("timeout") if "--" in call["argv"]]
    assert wrapped["argv"][5:10] == [str(programs / "op"), "run", "--environment", wrapped["argv"][8], "--"]
    assert wrapped["argv"][10] == str(programs / "jev-lint")
    expected_path = os.pathsep.join([str(programs), "/usr/bin", "/bin"])
    assert {call["path"] for call in tools.calls("op") + tools.calls("jev-lint")} == {expected_path}


@pytest.mark.parametrize("name", ["op", "jev-lint"])
def test_a_missing_program_skips_without_reading_the_keychain(
    record: session_store.SessionRecord, tools: Tools, programs: Path, name: str
) -> None:
    (programs / name).unlink()

    result = stop(record)

    assert "decision" not in result
    assert f"{name} is not installed" in result["systemMessage"]
    assert tools.calls("security") == []


@pytest.mark.parametrize("name", ["op", "jev-lint"])
@pytest.mark.parametrize("flaw", ["outside-store", "group-writable", "other-writable", "not-executable"])
def test_an_untrusted_program_is_refused_and_nothing_is_read_or_sent(
    record: session_store.SessionRecord,
    tools: Tools,
    programs: Path,
    tmp_path: Path,
    name: str,
    flaw: str,
) -> None:
    make_untrusted(programs / name, tmp_path, flaw)

    result = stop(record)

    assert "decision" not in result
    assert f"{name} is not trusted" in result["systemMessage"]
    assert tools.calls("security") == []
    assert tools.calls("op") == []


def make_untrusted(program: Path, tmp_path: Path, flaw: str) -> None:
    if flaw == "outside-store":
        elsewhere = tmp_path / "elsewhere" / program.name
        elsewhere.parent.mkdir()
        elsewhere.write_bytes(program.read_bytes())
        elsewhere.chmod(0o700)
        program.unlink()
        program.symlink_to(elsewhere)
    elif flaw == "group-writable":
        program.chmod(0o770)
    elif flaw == "other-writable":
        program.chmod(0o707)
    else:
        program.chmod(0o600)


def test_a_program_not_owned_by_the_trusted_owner_is_refused_and_nothing_is_read_or_sent(
    record: session_store.SessionRecord, tools: Tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(model_rules_programs, "TRUSTED_UID", os.getuid() + 1)

    result = stop(record)

    assert "decision" not in result
    assert "is not trusted (it is not owned by the trusted owner)" in result["systemMessage"]
    assert tools.calls("security") == []
    assert tools.calls("op") == []


def test_a_symlink_inside_the_store_to_a_trusted_program_is_accepted(programs: Path) -> None:
    link = programs / "op-link"
    link.symlink_to(programs / "op")

    assert model_rules_programs.resolve("op-link") == link


def test_a_directory_named_like_the_program_is_refused(programs: Path) -> None:
    (programs / "op").unlink()
    (programs / "op").mkdir()

    result = model_rules_programs.resolve("op")

    assert isinstance(result, Prevented)
    assert "op is not trusted" in result.reason


def test_a_trusted_program_is_found_in_a_later_directory_after_an_absent_one(
    programs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(model_rules_programs, "DIRECTORIES", (tmp_path / "absent", programs))

    assert model_rules_programs.resolve("op") == programs / "op"


def test_the_system_directories_are_the_root_owned_profiles_and_never_the_home_or_the_project() -> None:
    assert model_rules_programs.system_directories("alice") == (
        Path("/etc/profiles/per-user/alice/bin"),
        Path("/run/current-system/sw/bin"),
        Path("/nix/var/nix/profiles/default/bin"),
    )


def test_programs_must_really_live_in_the_nix_store_and_belong_to_root() -> None:
    assert model_rules_programs.DEFAULT_STORE_ROOT == Path("/nix/store")
    assert model_rules_programs.DEFAULT_OWNER_UID == 0
