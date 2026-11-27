---
status: accepted
date: 2026-11-27
supersedes: [ADR-0028]
related: [ADR-0010, ADR-0007]
---

# Hand approved lanes to herdr-core terminals

## Context and Problem Statement

ADR-0028 handed each lane to a T3 Code thread so that the human could follow and answer lanes on the desktop and
phone. T3 Code has since been removed from the human's machines (#280). The Herdr desktop app runs its terminals in
herdr-core, whose `hc` CLI starts programs in terminals that outlive their caller, and the Herdr iPhone app reaches
the same core over SSH; it does not see the older Herdr TUI that ADR-0010 used. Which transport should hand approved
lanes to their sessions now?

As before, the work state (Issue, plan comment, brief, pull request, `LANE-READY`) stays outside the transport, and a
terminal address is never the identity of the work (#181).

## Considered Options

- Start lanes with `hc run` in herdr-core terminals
- Go back to Herdr TUI panes (`herdr agent start`, ADR-0010)
- Let each lane report back with `hc send` into the parent

## Decision Outcome

Chosen option: "Start lanes with `hc run` in herdr-core terminals", because it is the only option that puts lanes
where the human watches and answers them on the desktop and the phone, while each lane keeps the hooks, guard, and
sandbox of a terminal session and the workflow stays in this repository's skills.

- A lane runs as `hc run --bg --no-parent --json --name <lane> --cwd <worktree> --label herdr.space=<repository>
    --label herdr.tab=<lane> claude|codex ... "<read the brief>"`. The labels make the Herdr app show the terminal.
    `--no-parent` keeps the lane alive when the parent's own terminal ends and keeps hc from typing notes into it.
- Waiting relies on the agent's own OSC 7501 status, which herdr-core stores and never guesses from the screen: Claude
    Code (2.1.295 and later) and Codex (0.163 and later) report it natively. Codex must run with `--no-daemon`, or its
    commands execute outside the terminal.
- The lane never sends text to the parent, through `hc send` or otherwise. hc wraps such a message in an `<hc from=...>`
    tag, but the tag is plain text in the parent's input that the parent cannot tell from something the user typed.
    The parent polls with `hc wait`, `hc get`, and `hc read` instead.
- hc has no worktree command, and the sandbox refuses writes to another repository's `.git/worktrees`, so the parent
    keeps creating the lane worktree with `herdr worktree create`, which already runs outside the sandbox and whose
    `~/.herdr/worktrees` root `cleanup_worktrees.py` sweeps.
- Every `hc` call runs outside the sandbox (`hc *`), since hc talks to the core through state under the home directory.
    The guard bounds what that may do: `hc run` starts only `claude` or `codex` by name, refuses any agent option other
    than the model, the effort, and Codex's `--no-daemon`, and asks for any other program, a template, another machine,
    or an hc option outside the lane form. `--cwd` must lie in this session's checkout or a lane worktree it created,
    because the lane's sandbox is rooted there. `hc send`, `hc kill`, and `hc rm` are allowed only for the addresses
    this session's own `hc run --json` printed, and only while `hc get` reports the same creation time for them: a
    name passes to a later terminal once the first finishes, and an address is unique only within one core. Other hc
    subcommands ask.
- A template named `claude` or `codex` would take precedence over the program, but templates live in
    `~/.config/herdr-core/templates`, outside every path the sandbox lets an agent write.

Going back to Herdr TUI panes was rejected because the Herdr iPhone app does not see the TUI, which leaves lanes out of
the human's reach away from the desk, as ADR-0028 already found. Reporting back with `hc send` was rejected because the
parent would have to trust text in its input that anyone could have typed.

### Consequences

- Good, because the human follows and answers every lane in the Herdr app on the desktop or the phone, and a lane's
    approval prompt reaches them through the agent's own blocked status.
- Good, because hc stays only the transport: the brief, plan, pull request, and `LANE-READY` carry the work, and the
    skill keeps the hc operations in a reference another transport can replace.
- Bad, because the whole `hc` command family runs outside the sandbox, and its safety rests on the guard's agent
    option list, the terminal ownership record, and herdr-core being trusted; every send, kill, or rm also waits on an
    `hc get` call.
- Bad, because lane worktrees still need the Herdr TUI's `herdr worktree create`, so the TUI cannot be removed until
    another way to create them exists.
- Bad, because waiting depends on the agents' OSC 7501 reports: an agent version without them would look working until
    it exits.
