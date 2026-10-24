# Contributing

## Check a Local Change

Render the working tree and verify the rendered output, as the `render` job in CI does. Use the
`agent-harness` revision locked in `flake.lock`, not whichever one is first on `PATH`: an older
release may not match this source. CI installs that revision with
[`install-agent-harness`](.github/actions/install-agent-harness/action.yml); where the flake does
not publish the package (it does so for macOS only), install it the same way, then run everything
inside `nix develop` so the locked binary and the declared tools are the ones used:

```sh
prefix="$(mktemp -d)"
nix develop --command agent-harness install --source agents --prefix "$prefix"
nix develop --command agent-harness verify --source agents --prefix "$prefix"
nix develop --command uv run pytest
nix develop --command bats tests/bootstrap_server.bats
```

Work flows through Issues, task worktrees, and reviewed pull requests; see
[`docs/DESIGN.md`](docs/DESIGN.md). Commit messages follow Conventional Commits. Record a decision
that is not obvious from the code as an ADR under [`docs/adr/`](docs/adr/).
