# ADR-0012: Keep the personal agent source in its own repository

- Status: Accepted
- Date: 2026-10-24
- Supersedes: [dotfiles ADR-0016](https://github.com/furedea/dotfiles/blob/main/docs/adr/0016_own_personal_agent_source.md),
  [dotfiles ADR-0030](https://github.com/furedea/dotfiles/blob/main/docs/adr/0030_bootstrap_the_agent_harness_on_servers_without_nix.md)

In the context of the personal agent-harness source that `furedea/dotfiles` ADR-0016 placed under
`agents/` and that ADR-0030 deployed to servers without Nix by cloning dotfiles, facing hosts that
must clone every machine setting just to render the harness, and a source whose history, tests, and
review have a different audience and cadence than the Nix machine configuration, we decided for
owning the source, its pytest and Bats tests, the server bootstrap script, and the ADRs about the
source in this repository, exporting the source as `packages.default` for dotfiles to read as a flake
input, and importing the history commit by commit from dotfiles, and against a monorepo with
agent-harness, a Claude Code or Codex plugin, and keeping the source in dotfiles, to let a Nix-less
server clone only the harness source while one renderer and one source still serve every machine and
the public engine stays free of personal policy, accepting that a source change reaches a Nix host
only after dotfiles updates its `agent-config` input, and that the bootstrap script keeps the
version-pinned, hash-unverified, x86_64-only downloads that ADR-0030 accepted.

Dotfiles keeps the Herdr and Moshi hook bundles, enabling `programs.agent-harness`, the GitHub App
token, `.agents/hooks/rules/`, and the package-installation ADRs. Imported commit messages keep their
original text with bare `#NNN` references rewritten to `furedea/dotfiles#NNN`. The moved ADRs were
renumbered from 0001; each records its dotfiles number.
