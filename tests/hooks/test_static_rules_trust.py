"""The shared style rules run only in repositories of trusted owners; a project's own rules run everywhere."""

import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import static_rule_scan

RECORD_CONFIGS = """
    import json, os, sys
    from pathlib import Path
    with Path(os.environ["SCANNER_CALLS"]).open("a") as stream:
        stream.write(sys.argv[3] + "\\n")
"""


@pytest.fixture
def shared_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / "shared-lint" / "sgconfig.yml"
    config.parent.mkdir()
    config.write_text("ruleDirs:\n  - rules\n")
    monkeypatch.setattr(static_rule_scan, "SHARED_CONFIG", config)
    return config


@pytest.fixture
def scanned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, executable: StubWriter) -> Path:
    calls = tmp_path / "configs.txt"
    monkeypatch.setenv("SCANNER_CALLS", str(calls))
    executable("ast-grep", RECORD_CONFIGS)
    return calls


def configs(calls: Path) -> list[str]:
    return calls.read_text().splitlines() if calls.exists() else []


def source_in(directory: Path) -> Path:
    path = directory / "source.py"
    path.write_text("print('x')\n")
    return path


def test_shared_rules_run_in_a_checkout_of_a_trusted_owner(
    tmp_path: Path, checkout_of: Callable[..., Path], shared_config: Path, scanned: Path
) -> None:
    static_rule_scan.diagnostics([source_in(checkout_of(tmp_path / "work"))])
    assert configs(scanned) == [str(shared_config)]


@pytest.mark.usefixtures("shared_config")
def test_shared_rules_do_not_run_in_a_checkout_of_another_owner(
    tmp_path: Path, checkout_of: Callable[..., Path], scanned: Path
) -> None:
    static_rule_scan.diagnostics([source_in(checkout_of(tmp_path / "work", "someone-else"))])
    assert configs(scanned) == []


@pytest.mark.usefixtures("checkout_of", "shared_config")
def test_shared_rules_do_not_run_outside_a_repository(tmp_path: Path, scanned: Path) -> None:
    directory = tmp_path / "loose"
    directory.mkdir()
    static_rule_scan.diagnostics([source_in(directory)])
    assert configs(scanned) == []


@pytest.mark.usefixtures("shared_config")
def test_a_projects_own_rules_run_in_a_checkout_of_another_owner(
    tmp_path: Path, checkout_of: Callable[..., Path], scanned: Path
) -> None:
    directory = checkout_of(tmp_path / "work", "someone-else")
    (directory / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
    static_rule_scan.diagnostics([source_in(directory)])
    assert configs(scanned) == [str(directory / "sgconfig.yml")]


@pytest.mark.usefixtures("shared_config")
def test_an_unreadable_trusted_owners_file_keeps_the_shared_rules_off(
    tmp_path: Path, checkout_of: Callable[..., Path], scanned: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = checkout_of(tmp_path / "work")
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"owners": []}))
    monkeypatch.setenv("AGENT_TRUSTED_OWNERS", str(broken))
    static_rule_scan.diagnostics([source_in(directory)])
    assert configs(scanned) == []


def test_shared_rules_ask_only_the_owner_not_whether_the_repository_is_a_fork(
    tmp_path: Path,
    checkout_of: Callable[..., Path],
    shared_config: Path,
    scanned: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Style is the owner's, so no network lookup slows each edit or turns the rules off when it gets no answer."""
    directory = checkout_of(tmp_path / "work")
    owners = tmp_path / "forks_excluded.json"
    owners.write_text(json.dumps({"owners": ["trusted-owner"], "exclude_forks": True}))
    monkeypatch.setenv("AGENT_TRUSTED_OWNERS", str(owners))

    def no_lookup(*_: object) -> None:
        raise AssertionError("the fork lookup must not run for style rules")

    monkeypatch.setattr(static_rule_scan.trusted_owners, "is_fork", no_lookup)
    static_rule_scan.diagnostics([source_in(directory)])
    assert configs(scanned) == [str(shared_config)]
