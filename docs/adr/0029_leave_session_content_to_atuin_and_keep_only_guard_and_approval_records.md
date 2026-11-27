---
status: accepted
date: 2026-11-27
amended:
  - "2026-11-27: atuin agent hooks are not installed, so the shell history stays human-only and an agent's shell exit codes are read from the thread content"
related: [ADR-0003, ADR-0005]
---

# Leave session content to atuin and keep only guard and approval records

## Context and Problem Statement

Improving the agent harness needs data on why a session went as it did: the instructions, the replies, the tool input and
output, the error flag, and the token usage. `audit_log.py` recorded per-tool-call metadata (tool name, touched paths,
`duration_ms`) and compaction counts, none of which says why. atuin threads store the missing content in one format for
several harnesses and redact secrets, so keeping both would hold the same facts twice and let the counts drift apart
through different filters. Which source is authoritative for each kind of information?

ADR-0005 bounded the audit log so the repository does not become a transcript store. That concern stands, but the
log no longer needs to cover tool calls, and atuin threads are not an audit log: their content lives outside this
repository, in atuin. Verified over 14 days, Claude Code tool results never exceeded the 64 KiB threads clip (0 of
37,458) and Codex's did 7 of 15,441 times, so the clip does not lose content that analysis needs.

## Considered Options

- Keep per-call and compaction records in `audit_log.py` and add atuin threads beside them
- Give each kind of information one authority: atuin threads for session content, Claude Code's transcript for
    compaction, the owner's hook for guard, approval and verification records
- Move all of it into the owner's hook by recording bodies there

## Decision Outcome

Chosen option: "Give each kind of information one authority", because each kind then has one place to read and no
second count to reconcile, and the hook records only the decisions that no other tool can know.

| Information | Authority |
| --- | --- |
| Conversation, tool input and output, diffs, error flag, token usage, approximate tool time (message timestamp differences) | atuin threads |
| Exit code of an agent's shell command | the tool result in the thread (Claude Code keeps `Exit code N` on a failed Bash result) |
| Compaction details (trigger, tokens before and after, duration) | `compact_boundary` lines in Claude Code's transcript |
| Guard decisions, approval denials, verification records | this repository's hooks |

- `audit_log.py` records only guard refusals (`Blocked`, `Escalated`) and approval denials (`PermissionDenied`). It no
    longer records per-tool-call events, touched paths of ordinary calls, `duration_ms`, or compaction. The hashed
    session id and worktree id stay, so a record can be joined with a thread.
- The hook registrations that fed the removed records are dropped for every harness, and the adapters lose their
    `audit` command.
- Verification records (`verification_session.py`) are unchanged.
- atuin agent hooks are not installed: shell history stays what a person typed, and the thread already holds an agent
    command's result and approximate time.
- Analysis reads atuin only through `atuin threads ... --format ndjson`, never its internal store, so #181 can later
    move these records into Durable State without changing the readers.

ADR-0005 stands for what remains in the log: metadata only, in the user's state directory, with retention and size
limits. This ADR narrows what the log covers and does not change those limits.

### Consequences

- Good, because the hook stops duplicating what atuin keeps and the numbers no longer depend on two filters.
- Good, because the remaining records are small, and fewer hooks run on every tool call.
- Bad, because analysis now needs atuin (threads enabled and synced) for session content, and a session atuin did not
    capture has no tool-level record here.
- Bad, because tool time is only approximate, taken from message timestamp differences instead of a measured duration.
