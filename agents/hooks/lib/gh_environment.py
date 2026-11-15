"""Check that the environment a gh call runs in leaves gh, git, ssh, and rg the programs the guard judged.

gh runs git, git runs ssh and other helpers, and the guard runs rg for its secret scan. Each of them,
their configuration, and the variables that redirect them must be out of the agent's reach, or the
call asks.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import gh_repository
from gh_command_line import (
    PROGRAM,
    CommandLine,
    has_inherited_function,
    has_writable_path_entry_before,
    in_agent_roots,
    is_system_program,
)

GITHUB_HOST = "github.com"
REMOTE_LOOKUP_TIMEOUT_SECONDS = 5
# Variables naming a file or directory a non-interactive shell sources before the command runs.
STARTUP_FILE_VARIABLES = ("BASH_ENV", "ENV", "ZDOTDIR")
# git settings that run a program for a transport, rewrite a URL to another transport, enable one,
# or pick a git-remote-<vcs> helper for a remote.
TRANSPORT_SETTINGS = (
    r"^(core\.(sshcommand|gitproxy)|url\..*\.(insteadof|pushinsteadof)|protocol\.(.*\.)?allow|remote\..*\.vcs)$"
)
# git settings that give a new clone hooks, or a filter program its checkout runs.
CHECKOUT_SETTINGS = (
    r"^(init\.templatedir|core\.(hookspath|fsmonitor|alternaterefscommand)|filter\..*\.(smudge|process))$"
)
# core.fsmonitor as a boolean selects git's built-in daemon; any other value is a program git runs.
# The filter settings `git lfs install` writes; any other filter command may be a shell running anything.
LFS_FILTER = re.compile(r"filter\.lfs\.(?:smudge git-lfs smudge -- %f|process git-lfs filter-process)")
BOOLEAN_FSMONITOR = re.compile(r"core\.fsmonitor (?:true|false|yes|no|on|off|1|0)?", re.IGNORECASE)
# The only http_unix_socket line gh's configuration may hold: the key with an empty value, at any level.
EMPTY_UNIX_SOCKET = re.compile(r"""\s*http_unix_socket:\s*(?:""|'')?\s*(?:#.*)?""")
CREDENTIAL_HELPERS = r"^credential\..*helper$"
SAFE_HELPER = re.compile(r"[A-Za-z0-9_./ -]+")
# The GIT_SSH_COMMAND the sandbox runtime sets: ssh through the proxy command the runtime itself provides.
SANDBOX_SSH_COMMAND = (
    "ssh -o ControlMaster=no -o ControlPath=none -o ProxyCommand=\"/bin/sh -c 'eval "
    "\\\"\\${SRT_SSH_PROXY_COMMAND:?unset, but GIT_SSH_COMMAND needs it}\\\"' sh '%h' %p\""
)
# Variables that make git run another program, or read configuration from a file the guard does not check.
GIT_OVERRIDE_VARIABLES = ("GIT_SSH", "GIT_EXEC_PATH", "GIT_PROXY_COMMAND", "GIT_ASKPASS", "SSH_ASKPASS")
GIT_OVERRIDE_VARIABLES += ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_ALLOW_PROTOCOL")


def environment_problem(line: CommandLine) -> str:
    """Why the environment may run something else than gh against github.com, or an empty string."""
    # gh runs git for clones, checkouts, and to find the working repository, and git runs ssh for SSH
    # remotes, so both must be as safe as gh.
    for name in (PROGRAM, "git", "ssh"):
        if problem := _stand_in_problem(name, line):
            return problem
    if os.environ.get("GH_FORCE_TTY"):
        return "the environment forces a terminal, so gh would start the pager program it names"
    if not is_system_program("rg"):
        return "PATH finds an rg this account could replace, so the secret scan cannot be trusted"
    if problem := _override_problem():
        return problem
    configured_repository = os.environ.get("GH_REPO")
    foreign_repository = configured_repository and gh_repository.repository(configured_repository) is None
    if os.environ.get("GH_HOST", GITHUB_HOST).lower() != GITHUB_HOST or foreign_repository:
        return "the environment sends gh to another host than github.com"
    return ""


def _override_problem() -> str:
    """Why the environment may run code in place of the checked shell, git, or ssh, or an empty string.

    GIT_SSH_COMMAND may be only plain ssh or the sandbox runtime's own value, whose ssh PATH finds and the
    stand-in check covers; any option could name another program, such as a ProxyCommand.
    """
    if any(os.environ.get(name) for name in STARTUP_FILE_VARIABLES):
        return "the environment names a startup file the shell sources first, which may redefine gh or git"
    ssh_command = os.environ.get("GIT_SSH_COMMAND", "ssh")
    if any(os.environ.get(name) for name in GIT_OVERRIDE_VARIABLES) or ssh_command not in {"ssh", SANDBOX_SSH_COMMAND}:
        return "the environment tells git to run another program than the checked ssh"
    if problem := _gh_config_problem():
        return problem
    transports = git_output("config", "--get-regexp", TRANSPORT_SETTINGS)
    if transports is None or transports.strip():
        return "git configuration rewrites URLs or names a transport program git may run"
    return ""


def _gh_config_problem() -> str:
    """Why gh's configuration may send its requests and token elsewhere, or an empty string."""
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    directory = Path(os.environ.get("GH_CONFIG_DIR") or Path(xdg) / "gh").absolute()
    if in_agent_roots(directory) or in_agent_roots(directory.resolve()):
        return "gh reads its configuration from a directory the agent can write"
    for name in ("config.yml", "hosts.yml"):
        try:
            lines = (directory / name).read_text().splitlines()
        except FileNotFoundError:
            continue
        except OSError:
            return f"gh's {name} cannot be read to check where it sends requests"
        if any("http_unix_socket" in line and not EMPTY_UNIX_SOCKET.fullmatch(line) for line in lines):
            return "gh's configuration may send its requests through a Unix socket"
    return ""


def _stand_in_problem(name: str, line: CommandLine) -> str:
    """Why something else than the installed program may run under its name, or an empty string."""
    if not line.single_call and has_writable_path_entry_before(name):
        return f"another command on the line could place a {name} earlier on PATH"
    if has_inherited_function(name):
        return f"the environment carries a shell function that bash would run instead of {name}"
    if shutil.which(name) is not None and not is_system_program(name):
        return f"PATH finds a {name} that this account could replace"
    return ""


def clone_may_run_code() -> bool:
    """Whether a new clone may run code: hooks from a template or hooks path, a filter, or a credential helper.

    A filter runs for any path whose .gitattributes, which the cloned repository supplies, names it.
    """
    if os.environ.get("GIT_TEMPLATE_DIR"):
        return True
    settings = _git_settings(CHECKOUT_SETTINGS)
    helpers = _git_settings(CREDENTIAL_HELPERS)
    if settings is None or helpers is None:
        return True
    if not all(_is_trusted_helper(value) for _, value in helpers):
        return True
    return not all(_is_installed_checkout_program(f"{key} {value}") for key, value in settings)


def _git_settings(pattern: str) -> list[tuple[str, str]] | None:
    """Each (key, value) git config reports for the pattern; None when git cannot be asked or a value spans lines."""
    output = git_output("config", "-z", "--get-regexp", pattern)
    if output is None:
        return None
    records = [record.partition("\n") for record in output.split("\0") if record]
    if any("\n" in value or "\r" in value for _, _, value in records):
        return None
    return [(key, value) for key, _, value in records]


def _is_trusted_helper(value: str) -> bool:
    """Whether a credential helper runs only a locked helper program with no arguments the shell could read.

    git runs a helper through the shell, so a `!` snippet, shell syntax, or a program such as sh with
    arguments may run anything. A reset, git-credential-<name>, an absolute git-credential-* path, or
    gh's own `gh auth git-credential` passes.
    """
    words = value.split()
    if not words:
        return True
    if not SAFE_HELPER.fullmatch(value):
        return False
    program = words[0]
    if program.startswith("/"):
        is_helper = (len(words) == 1 and Path(program).name.startswith("git-credential-")) or (
            Path(program).name == PROGRAM and words[1:] == ["auth", "git-credential"]
        )
        return is_helper and is_system_program(program)
    if len(words) != 1:
        return False
    git = shutil.which("git")
    root = Path(git).resolve().parent.parent if git else Path("/nonexistent")
    bundled = [root / directory / f"git-credential-{program}" for directory in ("libexec/git-core", "lib/git-core")]
    return is_system_program(next((str(path) for path in bundled if path.exists()), f"git-credential-{program}"))


def _is_installed_checkout_program(setting: str) -> bool:
    """Whether a checkout setting runs nothing, or is git-lfs's own filter, installed outside the agent roots."""
    if BOOLEAN_FSMONITOR.fullmatch(setting):
        return True
    return bool(LFS_FILTER.fullmatch(setting)) and is_system_program("git-lfs")


def git_output(*arguments: str) -> str | None:
    """What git prints for the arguments, or None when git cannot be asked or PATH finds one the agent can write.

    A planted git could tell the guard one remote and gh another, and would run inside the hook itself.
    """
    found = shutil.which("git")
    if found is None or not is_system_program("git"):
        return None
    try:
        return subprocess.run(
            [found, *arguments],
            capture_output=True,
            text=True,
            timeout=REMOTE_LOOKUP_TIMEOUT_SECONDS,
            check=False,
        ).stdout
    except OSError, subprocess.SubprocessError:
        return None
