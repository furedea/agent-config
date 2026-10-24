# ADR-0014: Check the agent-harness download against its release checksum

- Status: Accepted
- Date: 2026-10-24

In the context of the server bootstrap that
[ADR-0012](0012_keep_the_personal_agent_source_in_its_own_repository.md) kept with hash-unverified
downloads, where Nix hosts are the primary target and servers are secondary, facing an agent-harness
binary that renders the hooks guarding every agent, we decided for pinning its release version,
letting Renovate update the pin, and comparing the archive with the `.sha256` published beside it,
and against `gh attestation verify`, which needs a logged-in `gh` that servers rarely have, a
SHA-256 pinned in this repository, which adds a manual step to every version bump, and building
from source with `cargo`, which needs a Rust toolchain on the server, to keep the renderer matched to
this source and catch damaged downloads at no maintenance cost, accepting that a checksum from the
same release catches no forged release, so provenance on servers rests on GitHub and HTTPS as before
([Issue #8](https://github.com/furedea/agent-config/issues/8)).
