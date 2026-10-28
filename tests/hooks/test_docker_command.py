"""Docker runs outside the sandbox, so only read-only inspection passes without review."""

import pytest

from tests.runtime import load_script_module


guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


@pytest.mark.parametrize(
    "command",
    [
        "docker cp ./secrets.txt web:/tmp/",
        "docker create -v /Users/kaito/.ssh:/ssh alpine",
        "docker start web",
        "docker container run --rm alpine true",
        "docker compose run --rm web sh",
        "docker compose -f /Users/kaito/other/compose.yml ps",
        "docker volume create data",
        "docker buildx build .",
        "docker --context remote ps",
        "docker -H tcp://example.com:2375 ps",
        "docker-compose up",
        "docker-compose ps",
        "/usr/local/bin/docker cp a web:/tmp/",
        "docker ps && docker cp a web:/tmp/",
        "docker ps $FLAGS",
        "env docker cp a web:/tmp/",
        'bash -c "docker cp a web:/tmp/"',
        "echo a | xargs docker cp",
        "docker",
    ],
)
def test_docker_forms_other_than_read_only_inspection_ask(command: str) -> None:
    verdict = guard.decide("allowed", {"tool_input": {"command": command}})
    assert verdict.decision == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "docker ps",
        "docker ps -a --filter status=running",
        "docker images",
        "docker logs web",
        "docker logs --tail 50 web",
        "docker compose ps",
        "docker compose logs web",
        "docker ps | head -5",
    ],
)
def test_docker_read_only_inspection_passes(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "docker build .",
        "docker run alpine",
        "docker run --env-file /Users/kaito/.env alpine env",
        "docker exec web sh",
        "docker compose up",
        "docker compose down",
    ],
)
def test_forms_with_an_ask_prefix_are_left_to_the_provider_prompt(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "allow"


@pytest.mark.parametrize("command", ["docker rm web", "docker push img", "docker system prune", "docker volume rm v"])
def test_docker_deletion_and_publishing_stay_denied(command: str) -> None:
    assert guard.decide("forbidden", {"tool_input": {"command": command}}).decision == "deny"
