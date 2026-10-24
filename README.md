# agent-config

Personal source for [agent-harness](https://github.com/furedea/agent-harness): the provider-neutral
instructions, skills, hooks, and permission rules that render into `~/.claude` and `~/.codex`.

## Layout

| Path                         | Content                                                              |
| ---------------------------- | -------------------------------------------------------------------- |
| `agents/`                    | Harness source (source layout version 1)                             |
| `tests/`                     | pytest and Bats specifications for the source                        |
| `scripts/bootstrap_server.sh`| Installs the harness on servers without Nix                          |
| `docs/DESIGN.md`             | Development cycle, verification, and hook decisions                  |
| `docs/adr/`                  | Decisions about the source                                           |
| `CONTRIBUTING.md`            | How to check a local change                                          |
| `flake.nix`                  | `packages.default`: `agents/` with shebangs pinned to Python 3.14    |

## Use

With Nix, read `inputs.agent-config.packages.${system}.default` as the `source` of the agent-harness
Home Manager module. Without Nix, clone this repository and run `scripts/bootstrap_server.sh`.

## Bootstrap a Linux Server without Nix

On an x86_64 Linux server without Nix or root access, clone this repository and run the bootstrap:

```sh
mkdir -p "$HOME/ghq/github.com/furedea"
git clone https://github.com/furedea/agent-config \
  "$HOME/ghq/github.com/furedea/agent-config"
cd "$HOME/ghq/github.com/furedea/agent-config"
bash scripts/bootstrap_server.sh
. "$HOME/.config/agent-config/agent_env.sh"
```

The script downloads pinned x86_64 Linux release binaries (`agent-harness`, `shfmt`, `rg`, `jq`,
`ruff`, `dprint`, `shellcheck`, `bats`, and `uv`) into `~/.local/bin`, installs Python 3.14 through
uv, renders `agents/` into the home directory with the same `agent-harness` CLI, pins the hook
shebangs to that interpreter, keeps settings that Claude Code wrote at runtime, and writes
`~/.config/agent-config/agent_env.sh` for the login shell to source. It exits before installing
anything on other architectures; see the script for the source-build guidance.

The final command updates the current shell's `PATH`. Add the same line to `~/.profile` or
`~/.bashrc` to load the tools in future shells. To update an existing server, run:

```sh
cd "$HOME/ghq/github.com/furedea/agent-config"
git pull --ff-only
bash scripts/bootstrap_server.sh
```

Host-specific settings stay outside the repository in `~/.config/agent-config/`:
`bootstrap_server.env` sets locations such as `BIN_DIR`, `UV_PYTHON_INSTALL_DIR`, `UV_CACHE_DIR`,
and `XDG_CACHE_HOME` (see `--help`), and `claude_settings_override.json` is merged into the rendered
Claude Code settings. Hook state stays in `~/.local/state`. See
[ADR-0012](docs/adr/0012_keep_the_personal_agent_source_in_its_own_repository.md) for why the source
has its own repository.

## Verification and Hooks

Hooks register each session's worktree and verify changes automatically; state, expiry, the
300-second check budget, and the allow, ask, and deny policy are described in
[`docs/DESIGN.md`](docs/DESIGN.md). The development cycle there is how work reaches a merged pull
request.

## Develop

```sh
nix develop
uv run pytest
bats tests/bootstrap_server.bats
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) before checking a change with the rendered output.

The history up to the import comes from `furedea/dotfiles`; `#NNN` references in those commit
messages point at issues and pull requests of that repository.
