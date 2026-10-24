# agent-config

Personal source for [agent-harness](https://github.com/furedea/agent-harness): the provider-neutral
instructions, skills, hooks, and permission rules that render into `~/.claude` and `~/.codex`.

## Layout

| Path                         | Content                                                              |
| ---------------------------- | -------------------------------------------------------------------- |
| `agents/`                    | Harness source (source layout version 1)                             |
| `tests/`                     | pytest and Bats specifications for the source                        |
| `scripts/bootstrap_server.sh`| Installs the harness on servers without Nix                          |
| `docs/adr/`                  | Decisions about the source                                           |
| `flake.nix`                  | `packages.default`: `agents/` with shebangs pinned to Python 3.14    |

## Use

With Nix, read `inputs.agent-config.packages.${system}.default` as the `source` of the agent-harness
Home Manager module. Without Nix, clone this repository and run `scripts/bootstrap_server.sh`.

## Develop

```sh
nix develop
uv run pytest
bats tests/bootstrap_server.bats
```

The history up to the import comes from `furedea/dotfiles`; `#NNN` references in those commit
messages point at issues and pull requests of that repository.
