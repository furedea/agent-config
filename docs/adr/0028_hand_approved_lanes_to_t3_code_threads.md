---
status: proposed
date: 2026-11-21
supersedes: [ADR-0010]
related: [ADR-0007, ADR-0009]
---

# Hand approved lanes to T3 Code threads

## Context and Problem Statement

ADR-0010 hands each lane of an approved plan to a Claude or Codex session in a Herdr pane. The human then follows the
lanes in a terminal multiplexer on one machine, apart from the T3 Code app they already use on the desktop and phone.
T3 Code (0.1.10) runs Claude through the Agent SDK and Codex through the app-server, and on 2026-11-20 its threads
were checked to run the same PreToolUse, Stop and SessionStart hooks, the same command guard, the same sandbox, and the
same agent GitHub configuration as a terminal session. Its `t3 thread` CLI starts a thread in a new worktree, sends a
message to a thread, and waits for a reply. Which transport should hand approved lanes to their sessions?

The work state (Issue, plan comment, brief, pull request, `LANE-READY`) stays outside any transport, and a provider's
thread ID is never the identity of the work, so the interface and harness stay replaceable (#181). This decision
covers only the transport (#264).

## Considered Options

- Keep Herdr panes (ADR-0010)
- Start and drive lane threads with the `t3 thread` CLI
- T3's own `delegate_task`, subagents, or Agent Rooms

## Decision Outcome

Chosen option: "Start and drive lane threads with the `t3 thread` CLI", because it puts every lane in the one UI the
human already watches on the desktop and phone, where they also answer a lane's approval prompt or question, while the
lane keeps the hooks, guard and sandbox of a terminal session and the workflow stays in this repository's skills.

- A lane is started with `t3 thread start` and an explicit provider, in a worktree T3 creates for the lane's branch;
    the parent waits with `--wait` and reads the reply. A wait that ends because the lane needs an answer goes to the
    human in T3; the parent never answers it.
- Only `t3 thread *` runs outside the sandbox, as `herdr *` does for ADR-0010, because the T3 CLI writes T3's state
    under the home directory. Other `t3` subcommands stay sandboxed and ask.
- The command guard admits only the Claude and Codex provider instances, by name, and refuses an omitted provider, and it
    allows `t3 thread send` only to a thread this session started. A message sent to a thread runs as another agent's
    turn outside this session's control, so the guard bounds the recipients instead of reviewing the text.
- Antigravity is never a lane recipient, and the guard enforces that in code: its subscription terms do not allow
    another agent to drive it (google-antigravity/antigravity-cli#1493). The human may still use it in the T3 UI.
- Herdr support and `herdr-delegation` stay as the fallback until a later Issue removes them. ADR-0010's grants for
    Herdr forms stand until then.

Keeping Herdr was rejected because it leaves the lanes in a terminal on one machine, out of reach of the UI the human
uses. `delegate_task`, subagents and Agent Rooms were rejected because they move the delegation workflow (recipient
choice, brief, review, waiting, cleanup) into T3, so replacing T3 would mean rewriting the workflow, against #181.

### Consequences

- Good, because the human sees and answers every lane in one UI on any device, and lanes still run unattended to a pull
    request under the same hooks, guard and sandbox.
- Good, because T3 is only the transport: the brief, plan, pull request and `LANE-READY` carry the work, and the skill
    keeps the T3 operations in a reference that another transport can replace.
- Bad, because one more command family runs outside the sandbox, and its safety rests on the guard's provider list and
    thread ownership record and on the T3 server being trusted.
- Bad, because two transports coexist until Herdr is removed, and T3 worktrees under `~/.t3/worktrees` need their own
    cleanup next to Herdr's.
- Bad, because `--wait` has no timeout, so a lane that never replies holds the parent until the human intervenes.
