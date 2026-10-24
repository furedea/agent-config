"""Project allow rules count only from a trusted, non-fork owner decided by the origin URL."""

from collections.abc import Callable
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tests.runtime import CliRunner, REPO_ROOT, StubWriter, load_script_module

SetOrigin = Callable[[str], None]
AnswerGh = Callable[[str | None], Path]

trusted_owners = load_script_module("agents/hooks/lib/trusted_owners.py", "trusted_owners")
sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
guard_command = load_script_module("agents/hooks/guard_command.py", "guard_command")

CONFIG = REPO_ROOT / "agents/hooks/rules/trusted_owners.json"
# An approved gh prefix in a form the global rules do not list: only a project rule lets it through.
COMMAND = "gh label delete bug"
PROJECT_ALLOW = {
    "version": 1,
    "rules": [{"patterns": ["^gh label delete bug$"], "justification": "Project labels"}],
}


def test_trusted_owners_file_lists_furedea_and_excludes_forks() -> None:
    assert json.loads(CONFIG.read_text()) == {"owners": ["furedea"], "exclude_forks": True}


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        '{"owners": [], "exclude_forks": true}',
        '{"owners": ["furedea"]}',
        '{"owners": ["furedea"], "exclude_forks": "yes"}',
        '{"owners": ["", "furedea"], "exclude_forks": true}',
        '{"owners": "furedea", "exclude_forks": true}',
        '{"owners": ["furedea"], "exclude_forks": true, "extra": 1}',
    ],
)
def test_malformed_trusted_owners_are_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "trusted_owners.json"
    path.write_text(content)
    with pytest.raises(ValueError, match="invalid trusted owners"):
        trusted_owners.load(path)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/furedea/agent-config.git", ("furedea", "agent-config")),
        ("https://github.com/furedea/agent-config", ("furedea", "agent-config")),
        ("https://user:token@github.com/furedea/agent-config.git", ("furedea", "agent-config")),
        ("git@github.com:furedea/agent-config.git", ("furedea", "agent-config")),
        ("ssh://git@github.com/furedea/agent-config.git", ("furedea", "agent-config")),
        ("https://gitlab.com/furedea/agent-config.git", None),
        ("https://github.com/furedea", None),
        ("https://github.com/furedea/../x", None),
        ("/Users/kaito/ghq/github.com/furedea/agent-config", None),
        ("", None),
    ],
)
def test_the_owner_comes_from_the_origin_url(url: str, expected: tuple[str, str] | None) -> None:
    assert trusted_owners.parse_origin(url) == expected


@pytest.fixture
def project(git_project: Path) -> Path:
    policy = git_project / ".agents/hooks/rules/allowed_commands.json"
    policy.parent.mkdir(parents=True)
    policy.write_text(json.dumps(PROJECT_ALLOW))
    return git_project


@pytest.fixture
def origin(project: Path) -> SetOrigin:
    def set_url(url: str) -> None:
        subprocess.run(["git", "remote", "add", "origin", url], cwd=project, check=True, capture_output=True)

    return set_url


@pytest.fixture
def gh(executable: StubWriter, tmp_path: Path) -> AnswerGh:
    """Fake `gh api repos/<owner>/<repo> --jq .fork`; a None answer is a failed lookup."""
    calls = tmp_path / "gh_calls.txt"

    def answer(fork: str | None) -> Path:
        executable(
            "gh",
            f"""
            from pathlib import Path
            import sys
            Path({str(calls)!r}).open("a").write(" ".join(sys.argv[1:]) + "\\n")
            fork = {fork!r}
            if fork is None or sys.argv[1:2] != ["api"] or sys.argv[3:] != ["--jq", ".fork"]:
                sys.exit(1)
            print(fork)
            """,
        )
        return calls

    return answer


def decide(run_cli: CliRunner, kind: str = "allowed", command: str = COMMAND) -> subprocess.CompletedProcess[str]:
    return run_cli("agents/hooks/guard_command.py", kind, payload={"tool_input": {"command": command}})


def is_listed(result: subprocess.CompletedProcess[str]) -> bool:
    return result.returncode == 0 and result.stdout == ""


def test_a_listed_owner_that_is_not_a_fork_keeps_its_project_rules(
    run_cli: CliRunner, origin: SetOrigin, gh: AnswerGh
) -> None:
    origin("https://github.com/furedea/agent-config.git")
    calls = gh("false")
    assert is_listed(decide(run_cli))
    assert calls.read_text() == "api repos/furedea/agent-config --jq .fork\n"


def test_an_owner_not_in_the_list_loses_its_project_rules(run_cli: CliRunner, origin: SetOrigin, gh: AnswerGh) -> None:
    origin("https://github.com/someone/agent-config.git")
    calls = gh("false")
    result = decide(run_cli)
    assert '"permissionDecision":"ask"' in result.stdout
    assert not calls.exists()


def test_a_fork_of_a_listed_owner_loses_its_project_rules(run_cli: CliRunner, origin: SetOrigin, gh: AnswerGh) -> None:
    origin("https://github.com/furedea/agent-config.git")
    gh("true")
    assert '"permissionDecision":"ask"' in decide(run_cli).stdout


def test_a_failed_fork_lookup_loses_the_project_rules(run_cli: CliRunner, origin: SetOrigin, gh: AnswerGh) -> None:
    origin("https://github.com/furedea/agent-config.git")
    gh(None)
    assert '"permissionDecision":"ask"' in decide(run_cli).stdout


def test_a_missing_origin_loses_the_project_rules(run_cli: CliRunner, project: Path, gh: AnswerGh) -> None:
    calls = gh("false")
    assert '"permissionDecision":"ask"' in decide(run_cli).stdout
    assert not calls.exists()


def test_an_origin_that_is_not_github_loses_the_project_rules(
    run_cli: CliRunner, origin: SetOrigin, gh: AnswerGh
) -> None:
    origin("https://example.com/furedea/agent-config.git")
    gh("false")
    assert '"permissionDecision":"ask"' in decide(run_cli).stdout


def test_the_folder_name_does_not_make_an_owner_trusted(
    run_cli: CliRunner, project: Path, origin: SetOrigin, gh: AnswerGh
) -> None:
    assert "furedea" not in str(project)
    origin("https://github.com/someone/furedea.git")
    gh("false")
    assert '"permissionDecision":"ask"' in decide(run_cli).stdout


def test_a_successful_fork_lookup_is_remembered_per_repository(
    run_cli: CliRunner, origin: SetOrigin, gh: AnswerGh
) -> None:
    origin("https://github.com/furedea/agent-config.git")
    calls = gh("false")
    assert is_listed(decide(run_cli))
    assert is_listed(decide(run_cli))
    assert len(calls.read_text().splitlines()) == 1


def test_a_failed_fork_lookup_is_asked_again_next_time(run_cli: CliRunner, origin: SetOrigin, gh: AnswerGh) -> None:
    origin("https://github.com/furedea/agent-config.git")
    calls = gh(None)
    decide(run_cli)
    gh("false")
    assert is_listed(decide(run_cli))
    assert len(calls.read_text().splitlines()) == 2


def test_the_ignored_rules_are_announced_once_with_the_way_to_fix_it(
    run_cli: CliRunner, origin: SetOrigin, gh: AnswerGh
) -> None:
    origin("https://github.com/someone/agent-config.git")
    gh("false")
    first = json.loads(decide(run_cli).stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "trusted_owners.json" in first
    assert "someone" in first
    second = json.loads(decide(run_cli).stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "trusted_owners.json" not in second


def test_a_prompt_that_a_provider_turns_into_a_denial_still_carries_the_announcement(
    project: Path, origin: SetOrigin, gh: AnswerGh
) -> None:
    origin("https://github.com/someone/agent-config.git")
    gh("false")
    verdict = guard_command.decide("allowed", {"tool_input": {"command": COMMAND}}).hardened()
    assert verdict.decision == "deny"
    assert "trusted_owners.json" in verdict.reason


def test_the_announcement_also_reaches_a_command_the_project_rules_did_not_matter_for(
    run_cli: CliRunner, origin: SetOrigin, gh: AnswerGh
) -> None:
    origin("https://github.com/someone/agent-config.git")
    gh("false")
    result = decide(run_cli, command="ls")
    assert result.returncode == 0
    assert "trusted_owners.json" in json.loads(result.stdout)["systemMessage"]


def test_a_trusted_project_is_not_announced(run_cli: CliRunner, origin: SetOrigin, gh: AnswerGh) -> None:
    origin("https://github.com/furedea/agent-config.git")
    gh("false")
    assert decide(run_cli, command="ls").stdout == ""


def test_project_forbidden_rules_apply_whoever_owns_the_project(
    run_cli: CliRunner, project: Path, origin: SetOrigin, gh: AnswerGh
) -> None:
    origin("https://github.com/someone/agent-config.git")
    gh("false")
    forbidden = project / ".agents/hooks/rules/forbidden_commands.json"
    forbidden.write_text(
        json.dumps(
            {
                "version": 1,
                "rules": [{"patterns": ["^git status --porcelain$"], "justification": "Use the status wrapper."}],
            }
        )
    )
    result = decide(run_cli, kind="forbidden", command="git status --porcelain")
    assert result.returncode == 2
    assert "Use the status wrapper." in result.stderr
