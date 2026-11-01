"""Go forms that fetch code or change user-level configuration ask; local Go work passes."""

import pytest

from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


@pytest.mark.parametrize(
    "command",
    [
        "go env",
        "go env GOPATH GOFLAGS",
        "go env -json",
        "go run .",
        "go run ./cmd/x",
        "go run ./cmd/x -- --flag value",
        "go run -race ./cmd/x",
        "go run main.go",
        'go run "$PKG"',
        "go build ./...",
        "go test ./... -run TestX",
        "go vet ./...",
        "go list -m all",
        "go version",
        "go mod download",
        "go tool stringer -type=Kind",
        "go get example.com/module@v1.2.3",
        "go mod tidy",
        "go install example.com/tool@latest",
    ],
)
def test_local_go_work_passes_the_hook(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "go env -w GOFLAGS=-mod=mod",
        "go env -u GOFLAGS",
        "go env -json -w GOFLAGS=-x",
        "go env GOPATH -u GOFLAGS",
        "go run golang.org/x/tools/cmd/stringer@latest",
        "go run -race example.com/tool@v1.2.3 -- arg",
        "go run example.com/tool@v1.2.3",
        "env go run example.com/tool@latest",
    ],
)
def test_go_env_writes_and_remote_go_run_ask(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "ask"
