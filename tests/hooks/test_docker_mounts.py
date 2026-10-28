"""Docker runs outside the sandbox, so a bind mount of a secret path asks instead of passing silently."""

from pathlib import Path

import pytest

from tests.runtime import REPO_ROOT, load_script_module


guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")

HOME = str(Path.home())


@pytest.fixture(autouse=True)
def secret_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_SECRET_PATH_POLICY", str(REPO_ROOT / "agents/hooks/rules/secret_path_policy.json"))


def decide(command: str) -> guard.Verdict:
    return guard.decide("allowed", {"tool_input": {"command": command}})


@pytest.mark.parametrize(
    ("command", "named"),
    [
        pytest.param(
            "docker run --rm -v ~/.ssh:/x alpine cat /x/github_app.pem", "~/.ssh", id="short volume of a tilde path"
        ),
        pytest.param('docker run -v "$HOME:/h" alpine ls /h', "~", id="the home directory itself"),
        pytest.param(
            f"docker run --volume={HOME}/.ssh:/x alpine ls /x", "~/.ssh", id="long volume of an absolute path"
        ),
        pytest.param(
            "docker run --mount type=bind,source=$HOME/.ssh,target=/x alpine ls /x", "~/.ssh", id="bind mount source"
        ),
        pytest.param(
            "docker run --mount type=bind,src=~/.aws,dst=/x alpine ls /x", "~/.aws", id="bind mount src alias"
        ),
        pytest.param(
            "docker run -v ~/.ssh/github_app.pem:/k:ro alpine cat /k", "~/.ssh/github_app.pem", id="one secret file"
        ),
        pytest.param("docker run -v ~/.config:/c alpine ls /c", "~/.config", id="a parent of a protected path"),
        pytest.param(f"docker run -itv {HOME}/.kube:/k alpine ls /k", "~/.kube", id="a short option cluster"),
        pytest.param("docker create -v ~/.gnupg:/g alpine", "~/.gnupg", id="create"),
        pytest.param("docker container run -v ~/.ssh:/x alpine ls", "~/.ssh", id="container run"),
        pytest.param("docker container create -v ~/.ssh:/x alpine", "~/.ssh", id="container create"),
        pytest.param("docker compose run -v ~/.ssh:/x app ls", "~/.ssh", id="compose run"),
        pytest.param(
            "docker compose -f dev.yml run --rm -v ~/.ssh:/x app ls", "~/.ssh", id="compose run after options"
        ),
        pytest.param("docker -H ssh://host run -v ~/.ssh:/x alpine ls", "~/.ssh", id="run after a global option"),
    ],
)
def test_secret_bind_mounts_ask_and_name_the_path(command: str, named: str) -> None:
    verdict = decide(command)

    assert verdict.decision == "ask"
    assert named in verdict.reason


def test_the_reason_uses_the_review_format() -> None:
    verdict = decide("docker run -v ~/.ssh:/x alpine ls")

    assert verdict.reason.startswith("Needs review: docker bind mount")
    assert "Command: docker run -v" in verdict.reason


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("docker run -v data:/data alpine ls", id="named volume"),
        pytest.param("docker run -v ./src:/src alpine ls", id="project relative path"),
        pytest.param(
            "docker run -v src:/src:ro --mount type=volume,source=cache,target=/c alpine ls", id="volumes only"
        ),
        pytest.param("docker run --mount type=tmpfs,target=/t alpine ls", id="tmpfs"),
        pytest.param('docker run -v "$PWD:/w" alpine ls', id="the working directory"),
        pytest.param(f"docker run -v {HOME}/projects/app:/app alpine ls", id="a plain home subdirectory"),
        pytest.param("docker run alpine ls ~/.ssh", id="a path that is only an argument"),
        pytest.param("docker compose run app ls", id="compose without mounts"),
        pytest.param("docker compose -f ~/.ssh/c.yml run app ls", id="compose files are out of scope"),
        pytest.param("docker ps", id="listed inspection"),
        pytest.param("docker logs web", id="listed log reading"),
    ],
)
def test_other_docker_forms_are_not_asked_for_mounts(command: str) -> None:
    verdict = decide(command)

    assert "bind mount" not in verdict.reason


@pytest.mark.parametrize("command", ["docker ps", "docker compose logs web", "docker images"])
def test_read_only_inspection_stays_allowed(command: str) -> None:
    assert decide(command).decision == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            "docker run --mount=type=bind,source=/tmp,src=$HOME/.ssh,target=/x alpine", id="last source wins"
        ),
        pytest.param("docker run --mount Type=bind,Source=$HOME/.ssh,target=/x alpine", id="keys in any case"),
        pytest.param("docker run --mount type=BIND,source=$HOME/.ssh,target=/x alpine", id="type in any case"),
        pytest.param(f"docker run --mount 'type=bind,\"source={HOME}/.ssh\",target=/x' alpine", id="csv quoted field"),
        pytest.param(f"docker run -itv{HOME}/.ssh:/x alpine", id="cluster with an attached value"),
        pytest.param('docker run -itv"$HOME/.ssh:/x" alpine', id="cluster with a quoted attached value"),
        pytest.param("cd ~ && docker run -v .:/h alpine", id="dot after cd home"),
        pytest.param('cd ~/.ssh && docker run -v "$PWD":/x alpine', id="PWD after cd"),
        pytest.param("cd ~ && docker run -v ./.ssh:/x alpine", id="relative path after cd"),
        pytest.param("docker run -v $HOME/.SSH:/x alpine", id="case-insensitive file system"),
        pytest.param("docker-compose run -v ~/.ssh:/x app ls", id="standalone compose"),
    ],
)
def test_forms_that_hide_a_secret_mount_still_ask(command: str) -> None:
    assert decide(command).decision == "ask"


def test_a_mount_whose_source_is_known_only_at_run_time_asks() -> None:
    verdict = decide("docker run -v $SOURCE:/x alpine ls")

    assert verdict.decision == "ask"
    assert "run time" in verdict.reason


def test_a_mount_under_the_project_is_not_asked(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()

    verdict = decide(f"docker run -v {tmp_path}/data:/d alpine ls")

    assert "bind mount" not in verdict.reason
