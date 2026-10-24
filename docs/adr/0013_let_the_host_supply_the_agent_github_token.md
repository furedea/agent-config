# ADR-0013: Let the host supply the agent GitHub token

- Status: Accepted
- Date: 2026-10-24

In the context of agents that push and call `gh` inside the Claude Code sandbox with the agent
GitHub App token ([ADR-0008](0008_run_agent_git_inside_the_sandbox_with_unsigned_commits.md),
[ADR-0011](0011_close_the_sandbox_escape_and_run_nix_inside.md)), facing a source in this
repository that every host renders but only some hosts hold an App key for, we decided for the
host minting the token and opening GitHub in the sandbox, through the agent-harness Home Manager
module on Nix hosts and through `scripts/bootstrap_server.sh` when `bootstrap_server.env` names an
App ID and key path, and against listing GitHub domains and `GH_CONFIG_DIR` in
`agents/claude/settings.json` or requiring a token on every server, to keep the source free of
host secrets and let a server without a key still run the harness with GitHub closed, accepting
that the bootstrap mints the token once and leaves its five-minute refresh to a scheduler the host
owner installs, so an unscheduled server loses push access an hour after each bootstrap
([Issue #8](https://github.com/furedea/agent-config/issues/8)).
