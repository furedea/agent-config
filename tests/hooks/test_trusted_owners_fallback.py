"""The fork check falls back from gh to the public GitHub API and the declared repositories."""

from collections.abc import Callable
from email.message import Message
import http.client
import io
import json
from pathlib import Path
import subprocess
import sys
from typing import Self
import urllib.error
import urllib.request

import pytest

from tests.runtime import REPO_ROOT, StubWriter, load_script_module

pytestmark = pytest.mark.usefixtures("api")

SetOrigin = Callable[[str], None]
AnswerGh = Callable[[str | None], Path]

trusted_owners = load_script_module("agents/hooks/lib/trusted_owners.py", "trusted_owners")
sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
guard_command = load_script_module("agents/hooks/guard_command.py", "guard_command")

REAL_GITHUB_ANSWER = trusted_owners.github_answer
# An approved gh prefix in a form the global rules do not list: only a project rule lets it through.
COMMAND = "gh label delete bug"
PROJECT_ALLOW = {
    "version": 1,
    "rules": [{"patterns": ["^gh label delete bug$"], "justification": "Project labels"}],
}


def http_error(status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.github.com", status, "error", Message(), None)


class Reply(io.BytesIO):
    def __enter__(self) -> Self:
        return self


class PublicApi:
    """Fake of the unauthenticated GitHub API; `outcome` is a JSON body or the exception to raise."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.requests: list[tuple[urllib.request.Request, float | None]] = []
        self.outcome: str | Exception = urllib.error.URLError("offline")
        monkeypatch.setattr(urllib.request.OpenerDirector, "open", self.open)

    def open(self, request: urllib.request.Request, *, timeout: float | None = None) -> Reply:
        self.requests.append((request, timeout))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return Reply(self.outcome.encode())

    def answer(self, body: str) -> None:
        self.outcome = body

    def fail(self, error: Exception) -> None:
        self.outcome = error


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> PublicApi:
    """Every test starts offline, so no test reaches the real GitHub."""
    return PublicApi(monkeypatch)


@pytest.fixture(autouse=True)
def host_without_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every host starts without `gh`: the lookup through it never answers, until a test installs one."""

    def no_answer(*_: str) -> None:
        return None

    monkeypatch.setattr(trusted_owners, "github_answer", no_answer)


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
def gh(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AnswerGh:
    """Fake `gh api repos/<owner>/<repo> --jq .fork`; a None answer is a failed lookup."""
    calls = tmp_path / "gh_calls.txt"
    monkeypatch.setattr(trusted_owners, "github_answer", REAL_GITHUB_ANSWER)

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


def notice(command: str = COMMAND) -> str:
    verdict = guard_command.decide("allowed", {"tool_input": {"command": command}}).hardened()
    return verdict.reason


def is_ignored(command: str = COMMAND) -> bool:
    return "trusted_owners.json" in notice(command)


def trusted_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **overrides: object) -> None:
    config = {"owners": ["furedea"], "exclude_forks": True, "repositories": [], **overrides}
    path = tmp_path / "owners.json"
    path.write_text(json.dumps(config))
    monkeypatch.setenv("AGENT_TRUSTED_OWNERS", str(path))


@pytest.mark.usefixtures("project")
def test_a_failed_fork_lookup_loses_the_project_rules(origin: SetOrigin, gh: AnswerGh) -> None:
    origin("https://github.com/furedea/agent-config.git")
    gh(None)
    assert is_ignored()


@pytest.mark.usefixtures("project")
def test_a_failed_fork_lookup_is_asked_again_next_time(origin: SetOrigin, gh: AnswerGh) -> None:
    origin("https://github.com/furedea/agent-config.git")
    calls = gh(None)
    assert is_ignored()
    gh("false")
    assert not is_ignored()
    assert len(calls.read_text().splitlines()) == 2


@pytest.mark.usefixtures("project")
def test_without_gh_a_public_repository_is_asked_unauthenticated(origin: SetOrigin, api: PublicApi) -> None:
    origin("https://github.com/furedea/agent-config.git")
    api.answer('{"fork": false, "private": false}')
    assert not is_ignored()
    (request, timeout), *rest = api.requests
    assert rest == []
    assert request.full_url == "https://api.github.com/repos/furedea/agent-config"
    assert not {"authorization", "cookie"} & {name.lower() for name in request.headers}
    assert timeout is not None and 0 < timeout <= 10


@pytest.mark.usefixtures("project")
def test_without_gh_a_public_fork_loses_the_project_rules(origin: SetOrigin, api: PublicApi) -> None:
    origin("https://github.com/furedea/agent-config.git")
    api.answer('{"fork": true}')
    assert is_ignored()


@pytest.mark.usefixtures("project")
def test_the_public_answer_is_remembered_like_gh_answers(origin: SetOrigin, api: PublicApi) -> None:
    origin("https://github.com/furedea/agent-config.git")
    api.answer('{"fork": false}')
    assert not is_ignored()
    api.fail(urllib.error.URLError("offline"))
    assert not is_ignored()
    assert len(api.requests) == 1


@pytest.mark.usefixtures("project")
def test_gh_is_asked_first_and_the_api_is_left_alone(origin: SetOrigin, gh: AnswerGh, api: PublicApi) -> None:
    origin("https://github.com/furedea/agent-config.git")
    gh("false")
    assert not is_ignored()
    assert api.requests == []


@pytest.mark.usefixtures("project")
def test_a_declared_repository_is_answered_without_asking_gh_or_the_network(
    origin: SetOrigin, gh: AnswerGh, api: PublicApi, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted_config(tmp_path, monkeypatch, repositories=["furedea/agent-config"])
    origin("https://github.com/furedea/agent-config.git")
    calls = gh("true")
    assert not is_ignored()
    assert not calls.exists()
    assert api.requests == []


@pytest.mark.parametrize(
    "failure",
    [
        http_error(404),
        http_error(403),
        http_error(301),
        urllib.error.URLError("offline"),
        TimeoutError(),
        OSError("reset"),
        http.client.IncompleteRead(b""),
        http.client.BadStatusLine("x"),
        http.client.LineTooLong("status line"),
    ],
)
@pytest.mark.usefixtures("project")
def test_a_failed_public_lookup_of_any_kind_is_no_answer_and_never_raises(
    origin: SetOrigin, api: PublicApi, failure: Exception
) -> None:
    origin("git@github.com:furedea/private-tool.git")
    api.fail(failure)
    assert is_ignored()


@pytest.mark.usefixtures("project")
def test_a_slow_public_answer_is_cut_off_by_one_deadline_for_the_whole_exchange(
    origin: SetOrigin, api: PublicApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter(range(0, 1000, 2))
    monkeypatch.setattr(trusted_owners.time, "monotonic", lambda: next(ticks))
    origin("git@github.com:furedea/private-tool.git")
    api.answer('{"fork": false, "padding": "' + "x" * 100_000 + '"}')
    assert is_ignored()


@pytest.mark.usefixtures("project")
def test_a_public_answer_over_the_size_limit_is_no_answer(origin: SetOrigin, api: PublicApi) -> None:
    origin("git@github.com:furedea/private-tool.git")
    api.answer('{"fork": false, "padding": "' + "x" * 2_000_000 + '"}')
    assert is_ignored()


def test_the_public_lookup_never_follows_a_redirect() -> None:
    handlers = trusted_owners.public_opener().handlers
    assert not any(isinstance(handler, urllib.request.HTTPRedirectHandler) for handler in handlers)
    assert any(isinstance(handler, urllib.request.HTTPErrorProcessor) for handler in handlers)


@pytest.mark.usefixtures("project")
def test_a_fork_notice_does_not_ask_to_add_an_owner_that_is_already_trusted(origin: SetOrigin, api: PublicApi) -> None:
    origin("https://github.com/furedea/agent-config.git")
    api.answer('{"fork": true}')
    text = notice()
    assert "furedea/agent-config is a fork" in text
    assert "add the owner" not in text
    assert "trusted_owners.json" in text


@pytest.mark.parametrize("body", ["", "not json", "[]", "{}", '{"fork": "false"}', '{"fork": null}', '{"fork": 0}'])
@pytest.mark.usefixtures("project")
def test_an_unusable_public_answer_is_not_trusted_unless_declared(
    origin: SetOrigin,
    api: PublicApi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
) -> None:
    origin("git@github.com:furedea/private-tool.git")
    api.answer(body)
    assert is_ignored()
    trusted_config(tmp_path, monkeypatch, repositories=["furedea/private-tool"])
    assert not is_ignored()


@pytest.mark.usefixtures("project")
def test_the_shipped_declaration_covers_swe_conform_on_a_host_without_gh_or_a_public_answer(
    origin: SetOrigin, api: PublicApi
) -> None:
    origin("git@github.com:furedea/swe-conform.git")
    api.fail(http_error(404))
    assert not is_ignored()


@pytest.mark.usefixtures("project")
def test_a_repository_that_is_not_declared_stays_ignored_and_the_notice_names_each_failed_source(
    origin: SetOrigin, api: PublicApi
) -> None:
    origin("git@github.com:furedea/private-tool.git")
    api.fail(http_error(404))
    text = notice()
    assert "furedea/private-tool" in text
    assert "gh" in text
    assert "public GitHub API" in text
    assert "repositories" in text
    assert "trusted_owners.json" in text
    assert "agent-config" in text


@pytest.mark.usefixtures("project")
def test_the_declaration_matches_case_insensitively_and_by_exact_name(
    origin: SetOrigin, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted_config(tmp_path, monkeypatch, repositories=["Furedea/SWE-Conform"])
    origin("git@github.com:furedea/swe-conform.git")
    assert not is_ignored()


@pytest.mark.usefixtures("project")
def test_a_declared_name_does_not_cover_a_different_repository(
    origin: SetOrigin, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted_config(tmp_path, monkeypatch, repositories=["furedea/swe-conform"])
    origin("git@github.com:furedea/swe-conform-fork.git")
    assert is_ignored()


@pytest.mark.usefixtures("project")
def test_a_declared_repository_of_an_untrusted_owner_stays_untrusted(
    origin: SetOrigin,
    api: PublicApi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted_config(tmp_path, monkeypatch, repositories=["someone/swe-conform"])
    origin("git@github.com:someone/swe-conform.git")
    assert is_ignored()
    assert api.requests == []


@pytest.mark.usefixtures("project")
def test_a_declaration_is_not_needed_when_forks_are_not_excluded(
    origin: SetOrigin, api: PublicApi, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted_config(tmp_path, monkeypatch, exclude_forks=False)
    origin("git@github.com:furedea/private-tool.git")
    assert not is_ignored()
    assert api.requests == []


@pytest.mark.usefixtures("project")
def test_a_declaration_is_not_written_to_the_cache(
    origin: SetOrigin, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted_config(tmp_path, monkeypatch, repositories=["furedea/swe-conform"])
    origin("git@github.com:furedea/swe-conform.git")
    assert not is_ignored()
    trusted_config(tmp_path, monkeypatch, repositories=[])
    assert is_ignored()


@pytest.mark.usefixtures("api")
def test_a_project_cannot_widen_the_declaration(project: Path, origin: SetOrigin) -> None:
    origin("git@github.com:furedea/private-tool.git")
    (project / ".agents/hooks/rules/trusted_owners.json").write_text(
        json.dumps({"owners": ["furedea"], "exclude_forks": True, "repositories": ["furedea/private-tool"]})
    )
    assert is_ignored()
