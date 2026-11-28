---
status: accepted
date: 2026-11-27
related: [ADR-0028, ADR-0010, ADR-0007]
---

# Offer herdr-core terminals as an alternative lane transport

## Context and Problem Statement

ADR-0028 hands each lane to a T3 Code thread so that the human can follow and answer lanes on the desktop and the
phone. The Herdr desktop app runs its terminals in herdr-core, whose `hc` CLI starts programs in terminals that outlive
their caller, and the Herdr iPhone app reaches the same core over SSH; it does not see the older Herdr TUI that
ADR-0010 used. The human wants to follow lanes in the Herdr app as well, and to keep lanes running when T3 Code is
unavailable (#280). How should herdr-core carry lanes next to T3 Code?

As before, the work state (Issue, plan comment, brief, pull request, `LANE-READY`) stays outside the transport, and a
terminal address is never the identity of the work (#181).

## Considered Options

- Start lanes with `hc run` in herdr-core terminals as an alternative, keeping T3 Code the default
- Replace T3 Code with herdr-core terminals
- Keep T3 Code as the only transport
- Go back to Herdr TUI panes (`herdr agent start`, ADR-0010)
- Let each lane report back with `hc send` into the parent

## Decision Outcome

Chosen option: "Start lanes with `hc run` in herdr-core terminals as an alternative, keeping T3 Code the default",
because it puts lanes in the Herdr app when the human asks for it or T3 Code is unavailable, while T3 Code keeps
carrying lanes as ADR-0028 decided, and each lane keeps the hooks, guard, and sandbox of a terminal session either way.

- T3 Code stays the default transport. The parent uses herdr-core when the user asks for the Herdr app or `hc`, or when
    T3 Code is unavailable and herdr-core is available; with neither, it starts no lane. Herdr TUI panes stay deprecated
    and are never a fallback.
- Every `hc` command starts a core when none runs, and that core and its terminals inherit the calling shell's
    environment, so the Herdr app must be running before the first `hc` call; the parent asks the user to confirm it.

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

Replacing T3 Code was rejected because the human keeps T3 Code for lanes, and its guard, ownership records, and cleanup
already work (ADR-0028). Keeping T3 Code alone was rejected because lanes would stop whenever T3 Code is unavailable and
would never show in the Herdr app. Going back to Herdr TUI panes was rejected because the Herdr iPhone app does not see
the TUI, which leaves lanes out of the human's reach away from the desk, as ADR-0028 already found. Reporting back with `hc send` was rejected because the
parent would have to trust text in its input that anyone could have typed.

### Consequences

- Good, because the human can follow and answer lanes in the Herdr app on the desktop or the phone, and a lane's
    approval prompt reaches them through the agent's own blocked status; lanes also run when T3 Code is unavailable.
- Bad, because two transports, each with its own guard rules, ownership record, and reference, must be kept working.
- Good, because hc stays only the transport: the brief, plan, pull request, and `LANE-READY` carry the work, and the
    skill keeps the hc operations in a reference another transport can replace.
- Bad, because the whole `hc` command family runs outside the sandbox, and its safety rests on the guard's agent
    option list, the terminal ownership record, and herdr-core being trusted; every send, kill, or rm also waits on an
    `hc get` call.
- Bad, because lane worktrees still need the Herdr TUI's `herdr worktree create`, so the TUI cannot be removed until
    another way to create them exists.
- Bad, because waiting depends on the agents' OSC 7501 reports: an agent version without them would look working until
    it exits.
