"""A gh call joined only with commands that write nothing is judged as gh alone (#255).

PATH holds an entry the agent can write before gh in every test here, as in the sandboxed harness. A
command that writes no file cannot plant a stand-in there, so beside such commands the call is judged by
the gh policy table alone. A literal cd keeps that, and gh's working repository is checked in every
directory the call may run in. A line that may write a program, change PATH, or run code it does not show
still asks. Between the hook's check and the run the files may change (TOCTOU); #181 closes that gap.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
gh_command_line = sys.modules["gh_command_line"]
shell_syntax = sys.modules["shell_syntax"]
pytestmark = pytest.mark.usefixtures("plain_gh_environment", "writable_path_entry")
TRUSTED = "https://github.com/furedea/agent-config.git"


def decide(command: str) -> str:
    return guard.decide("allowed", {"tool_input": {"command": command}}).decision


def checkout(directory: Path, url: str) -> Path:
    directory.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "--quiet"], check=True, cwd=directory)
    subprocess.run(["git", "remote", "add", "origin", url], check=True, capture_output=True, cwd=directory)
    return directory


@pytest.fixture
def writable_path_entry(isolated_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty directory the agent can write, searched before gh, git, and ssh."""
    entry = isolated_project / "later"
    entry.mkdir()
    monkeypatch.setenv("PATH", f"{entry}:{os.environ['PATH']}")
    return entry


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            "gh pr checks 240 -R furedea/agent-config 2>&1 | grep -c pass", id="a filter and a copied stderr"
        ),
        pytest.param("gh pr view 1 -R furedea/agent-config 2>/dev/null | jq .x | head -3", id="output to /dev/null"),
        pytest.param("gh pr list -R furedea/agent-config | awk '{print $1}' | sort | uniq -c", id="awk sort uniq"),
        pytest.param("sleep 5; gh pr checks 1 -R furedea/agent-config | tail -3; echo done", id="sleep and echo"),
        pytest.param("ls docs; wc -l notes.txt; gh pr view 1 -R furedea/agent-config", id="ls and wc"),
        pytest.param("sed -n 1,5p notes.txt; gh pr view 1 -R furedea/agent-config", id="sed printing lines"),
        pytest.param("sed -n '/^## A/,/^## B/p' notes.txt; gh pr view 1 -R furedea/agent-config", id="sed by pattern"),
        pytest.param("gh api repos/furedea/r/contents/f --jq .content | base64 -d | head", id="base64 decoding"),
        pytest.param("gh pr view 1 -R furedea/agent-config > notes.txt", id="output to a directory off PATH"),
    ],
)
def test_gh_beside_commands_that_write_nothing_is_judged_alone(command: str) -> None:
    assert decide(command) == "allow"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_read_of_the_working_repository_beside_read_only_commands_follows_its_remote() -> None:
    assert decide("ls docs; gh pr view 1 | head -3") == "allow"
    subprocess.run(["git", "remote", "set-url", "origin", "https://evil.example/o/r"], check=True)
    assert decide("ls docs; gh pr view 1 | head -3") == "ask"


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("cp x later/gh; gh pr list -R furedea/agent-config", id="cp a stand-in for gh"),
        pytest.param("cp x later/git; gh pr list -R furedea/agent-config", id="cp a stand-in for git"),
        pytest.param("mv x later/gh; gh pr list -R furedea/agent-config", id="mv"),
        pytest.param("ln -s /bin/sh later/gh; gh pr list -R furedea/agent-config", id="ln"),
        pytest.param("install x later/gh; gh pr list -R furedea/agent-config", id="install"),
        pytest.param("chmod +x later/gh; gh pr list -R furedea/agent-config", id="chmod"),
        pytest.param("export PATH=later:$PATH; gh pr list -R furedea/agent-config", id="export PATH"),
        pytest.param("echo x > later/gh; gh pr list -R furedea/agent-config", id="a redirect into a PATH entry"),
        pytest.param("gh pr list -R furedea/agent-config > later/gh; echo done", id="gh output into a PATH entry"),
        pytest.param("echo x > $DIR/gh; gh pr list -R furedea/agent-config", id="a redirect named at run time"),
        pytest.param(
            "echo '[diff] external = ./x' >> .git/config; git diff; gh api repos/furedea/agent-config/pulls",
            id="a write to git configuration a later git read runs",
        ),
        pytest.param(
            "echo x > notes.txt; gh api repos/furedea/agent-config/pulls", id="another command writing a file"
        ),
        pytest.param(
            "gh api repos/furedea/agent-config/contents/x > .git/config; git status", id="gh writing what git reads"
        ),
        pytest.param("printf $OPT PATH /tmp; gh pr list -R furedea/agent-config", id="printf with a run-time word"),
        pytest.param("echo $WORDS; gh pr list -R furedea/agent-config", id="echo with a run-time word"),
        pytest.param("{ echo x; } > later/gh; gh pr list -R furedea/agent-config", id="a redirect on a block"),
        pytest.param("(echo x) > later/gh; gh pr list -R furedea/agent-config", id="a redirect on a subshell"),
        pytest.param("if true; then echo x; fi > later/gh; gh pr list -R furedea/agent-config", id="on an if"),
        pytest.param(
            "{ echo x; } >> .git/config; gh api repos/furedea/agent-config/pulls",
            id="a block writing git configuration",
        ),
        pytest.param("sort -o later/gh x; gh pr list -R furedea/agent-config", id="sort -o"),
        pytest.param("sort -uo later/gh x; gh pr list -R furedea/agent-config", id="sort -o in a bundle"),
        pytest.param("sort --compress-program=x y; gh pr list -R furedea/agent-config", id="sort running a program"),
        pytest.param("uniq x later/gh; gh pr list -R furedea/agent-config", id="uniq with an output file"),
        pytest.param("base64 -d -o later/gh x; gh pr list -R furedea/agent-config", id="base64 -o"),
        pytest.param("awk '{print > \"later/gh\"}' x; gh pr list -R furedea/agent-config", id="awk writing"),
        pytest.param("awk 'BEGIN{system(\"x\")}'; gh pr list -R furedea/agent-config", id="awk running a program"),
        pytest.param("awk -f prog.awk x; gh pr list -R furedea/agent-config", id="awk reading its program"),
        pytest.param("sed -n 'w later/gh' x; gh pr list -R furedea/agent-config", id="sed writing"),
        pytest.param("sed -i s/a/b/ x; gh pr list -R furedea/agent-config", id="sed in place"),
        pytest.param("git status -sb; gh pr list -R furedea/agent-config", id="a git read, left to #181"),
        pytest.param("git log --oneline -3 | head; gh pr list -R furedea/agent-config", id="a git log"),
        pytest.param("git commit -m x; gh pr list -R furedea/agent-config", id="a git write"),
        pytest.param("python3 x.py; gh pr list -R furedea/agent-config", id="another program"),
    ],
)
def test_a_line_that_may_plant_a_program_or_change_path_still_asks(command: str) -> None:
    assert decide(command) == "ask"


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("cat <<'EOF' | head -1\nx\nEOF\ngh pr list -R furedea/agent-config", id="a heredoc"),
        pytest.param("head <<< x; gh pr list -R furedea/agent-config", id="a herestring"),
        pytest.param("echo $(ls); gh pr list -R furedea/agent-config", id="a command substitution"),
        pytest.param("cat <(ls); gh pr list -R furedea/agent-config", id="a process substitution"),
        pytest.param("for n in 1 2; do echo $n; done; gh pr list -R furedea/agent-config", id="a loop"),
        pytest.param("f() { ls; }; f; gh pr list -R furedea/agent-config", id="a function"),
        pytest.param("N=1; gh pr list -R furedea/agent-config", id="an assignment"),
    ],
)
def test_a_line_building_text_or_assigning_still_asks(command: str) -> None:
    assert decide(command) == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_literal_cd_judges_the_working_repository_where_gh_runs(isolated_project: Path) -> None:
    trusted = checkout(isolated_project / "trusted", TRUSTED)
    foreign = checkout(isolated_project / "foreign", "https://evil.example/o/r")
    assert decide(f"cd {trusted}; gh pr view 244 --json body --jq .body") == "allow"
    assert decide("cd trusted && gh pr list | head -3") == "allow"
    assert decide(f"cd {foreign}; gh pr view 244 --json body --jq .body") == "ask"
    assert decide(f"cd {foreign}; gh pr view 244 -R furedea/agent-config") == "allow"


@pytest.mark.usefixtures("isolated_project")
def test_a_cd_also_judges_the_directory_gh_runs_in_when_the_cd_fails(isolated_project: Path) -> None:
    checkout(isolated_project, "https://evil.example/o/r")
    trusted = checkout(isolated_project / "trusted", TRUSTED)
    assert decide(f"cd {trusted}; gh pr view 1") == "ask"


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("cd missing; gh pr list", id="a directory that does not exist"),
        pytest.param("cd $DIR; gh pr list", id="a directory named at run time"),
        pytest.param("cd -; gh pr list", id="the previous directory"),
        pytest.param("pushd trusted; gh pr list", id="pushd"),
        pytest.param("cd -P trusted; gh pr list", id="an option"),
    ],
)
def test_a_cd_the_hook_cannot_follow_still_asks(command: str, isolated_project: Path) -> None:
    checkout(isolated_project / "trusted", TRUSTED)
    assert decide(command) == "ask"


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize("entry", [".", ""])
def test_a_cd_asks_while_path_holds_a_relative_entry(
    entry: str, isolated_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = checkout(isolated_project / "trusted", TRUSTED)
    assert decide(f"cd {trusted}; gh pr list -R furedea/agent-config") == "allow"
    monkeypatch.setenv("PATH", f"{os.environ['PATH']}:{entry}")
    assert decide(f"cd {trusted}; gh pr list -R furedea/agent-config") == "ask"


@pytest.mark.usefixtures("isolated_project")
def test_a_cd_up_from_a_symlink_judges_the_logical_parent(
    isolated_project: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    checkout(isolated_project, TRUSTED)
    foreign = checkout(isolated_project / "foreign", "https://evil.example/o/r")
    target = checkout(tmp_path_factory.mktemp("elsewhere") / "trusted", TRUSTED)
    (foreign / "link").symlink_to(target)
    assert decide("cd foreign/link; gh pr view 1") == "allow"
    assert decide("cd foreign/link; cd ..; gh pr view 1") == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_relative_cd_asks_while_cdpath_may_send_it_elsewhere(
    isolated_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = checkout(isolated_project / "trusted", TRUSTED)
    assert decide("cd trusted; gh pr list") == "allow"
    monkeypatch.setenv("CDPATH", str(isolated_project / "elsewhere"))
    assert decide("cd trusted; gh pr list") == "ask"
    assert decide(f"cd {trusted}; gh pr list") == "allow"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_cd_asks_while_the_environment_carries_a_cd_function(
    isolated_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = checkout(isolated_project / "trusted", TRUSTED)
    monkeypatch.setenv("BASH_FUNC_cd%%", "() {  builtin cd /\n}")
    assert decide(f"cd {trusted}; gh pr list -R furedea/agent-config") == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_cd_to_a_name_after_a_double_dash_is_not_followed(isolated_project: Path) -> None:
    checkout(isolated_project / "-foreign", "https://evil.example/o/r")
    source = "cd -- -foreign; gh pr list"
    line = gh_command_line.command_line(source, shell_syntax.parse(source))
    assert line.changes_directory
    assert decide(source) == "ask"
