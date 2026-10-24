# Contributing

## Check a Local Change

Render the working tree and verify the rendered output, as the `render` job in CI does. Use the
`agent-harness` revision locked in `flake.lock` (CI installs it with
[`install-agent-harness`](.github/actions/install-agent-harness/action.yml)), not whichever one is
first on `PATH`: an older release may not match this source.

```sh
prefix="$(mktemp -d)"
agent-harness install --source agents --prefix "$prefix"
nix develop --command agent-harness verify --source agents --prefix "$prefix"
uv run pytest
bats tests/bootstrap_server.bats
```

Work flows through Issues, task worktrees, and reviewed pull requests; see
[`docs/DESIGN.md`](docs/DESIGN.md). Commit messages follow Conventional Commits. Record a decision
that is not obvious from the code as an ADR under [`docs/adr/`](docs/adr/).
