# herdr-core Transport

The [delegation](../SKILL.md) operations for lanes in herdr-core terminals, through the `hc` CLI of
the Herdr desktop app. herdr-core is the default transport; the Herdr app on the desktop and the
iPhone shows its terminals. Checked against hc 0.1.22 (`hc --help`, `hc --skill`, and
[herdr-core](https://github.com/herdrdev/herdr-core) `schema/hc.openrpc.json`); the decision is
ADR-0030.

## Prerequisites

- herdr-core is available when `hc ls --json` succeeds as an ordinary Bash call: the core runs and
    the installed sandbox settings let `hc` leave the sandbox, which they do only together with the
    [Guard Contract](#guard-contract). Otherwise start no lane: report the reason to the user, as
    [Branches and worktrees](../../development-cycle/references/branches.md) describes, and never
    switch to another transport on your own. Do not start, stop, restart, or update the core.
- An implementation lane also needs `herdr worktree create`, since hc has no worktree command and
    the sandbox refuses writes to another repository's `.git/worktrees`. It works when
    `herdr workspace list` succeeds; otherwise start no implementation lane and report the reason.
    A plan review creates no worktree and needs only the first condition.
- Run each `hc` and `herdr` command as its own Bash call, with nothing chained, substituted, or
    redirected around it, and every word literal. Only such a call passes the guard unprompted; a
    pipe into a read-only filter such as `jq` is the one addition it accepts.
- Run `git fetch origin` in a separate call before Start.

## Recipients

- Start Claude as `claude --model sonnet --effort medium "<message>"` and Codex as
    `codex --no-daemon --model gpt-6.1-sol "<message>"`. Codex needs `--no-daemon`, or its commands
    execute outside the terminal. Both report their state through OSC 7501 (Claude Code 2.1.295 and
    later, Codex 0.163 and later), which is all that `hc wait` and `hc get` read.
- Antigravity is never a recipient: its terms forbid another agent driving it on a subscription
    ([google-antigravity/antigravity-cli#1493](https://github.com/google-antigravity/antigravity-cli/issues/1493)).
- Do not start a lane from an hc template: the guard cannot see the command a template runs.

## Guard Contract

The command hooks hold `hc` to this contract; a call outside it is denied or asks.

- `run` starts only `claude` or `codex` by name, with `--bg`, `--no-parent`, `--json`, `--name`, and
    `--cwd`, optionally `--label`, and exactly one message after the agent's options. A message of
    one word asks, since it may be a subcommand such as `claude update`. An agent option other than `--model` and `--effort` for Claude, or `--no-daemon` and `--model` for Codex,
    is denied: it could switch off the agent's sandbox, hooks, or approvals. Another program, a
    template, `--on`, and any other hc option ask.
- `run --cwd` takes an absolute path inside this session's checkout or inside a worktree this
    session created with `herdr worktree create`; any other directory asks, since the lane's sandbox
    is rooted where it starts.
- `send`, `kill`, and `rm` run only on an address this session started, which the hooks learn from
    the `address` and `created_ms` that a successful plain `hc run --json` prints; before each call
    they ask the core with `hc get` that the address still names that terminal. A name asks, since a
    later terminal can take it once the first finishes; any other address may be the user's or the
    parent's, and a core that cannot answer cannot vouch for one.
- `ls`, `get`, `read`, `wait` with a terminal, `templates`, `--help`, `--version`, and `--skill` run
    as reads. Every other subcommand (`exec`, `file`, `keys`, `interrupt`, `attach`, `machine`,
    `server`, and the rest) and `send --force` ask.

## Operations

- **Start** an implementation lane, each line as its own call:

    ```bash
    herdr workspace list                                         # is the primary checkout already open?
    herdr workspace create --cwd <primary-checkout> --label <repo> --no-focus   # only when it is not open
    herdr worktree create --workspace <primary-id> --branch <branch> --base origin/<base> --label <branch> --no-focus
    hc run --bg --no-parent --json --name <lane-name> --cwd <worktree> --label herdr.space=<repo> --label herdr.tab=<lane-name> claude --model sonnet --effort medium "Read your brief at <scratchpad>/briefs/<lane-name>.md and carry it out."
    ```

    Pass `<primary-id>` from `.result.workspace.workspace_id` of the list or create output, and take
    `<worktree>` from `.result.worktree.path` of the `worktree create` output; never predict either.
    Before `worktree create`, check that `<branch>` exists neither locally nor in another worktree
    (`git branch --list <branch>` and `git worktree list`, each as its own call). `<lane-name>`
    matches `[a-z0-9_-]{1,32}` and is not live in `hc ls`. The `herdr.space` and `herdr.tab` labels
    make the Herdr app show the terminal; `--no-parent` keeps the lane alive when this session's own
    terminal ends and keeps hc from typing notes into it. `run --json` prints the terminal; keep its
    `address`, such as `t7`, as the recipient identity, and use that address, never the name, in
    every later call.
- **Start** a plan review the same way, without the `herdr` calls and with `--cwd` set to the
    checkout under review, which must be this session's own. The brief assigns a review only, so the reviewer reads and does not edit;
    that checkout keeps its single writer.
- **Wait** in the background. `hc wait` returns as soon as the lane is not working, so judge each
    return by the lane's turn, which goes up each time its status leaves `working`. Record the turn
    before the call that starts the work: `0` for a Start, and `turn` from `hc get <address> --json`
    right before a Prompt. Then repeat:
    1. Run `hc wait <address> --timeout 1800 --json` as its own background call. It prints
        `{"terminal", "ended", "reason", "status", "turn", "exit_code"}`, where `status` is the
        agent's own word: `working`, `idle`, `done`, `blocked`, or `error`.
    2. Decide, in this order:
        - `reason` is `exit`, or `status` is `error`: the lane stopped or failed. Read its screen and
            report the cause to the user; do not restart it unasked.
        - `status` is `blocked`: the lane waits for an answer to an approval or a question. The user
            answers it in the Herdr app; the parent never answers it, through `send --force`, `keys`,
            or otherwise. Tell the user which lane waits, then wait with a background `sleep 300`,
            which contains no `hc`, and return to step 1.
        - `status` is `idle` or `done` and `turn` is above the recorded turn: the turn ended. Read
            the reply.
        - `status` is `idle` or `done` and `turn` is not above it: the work has not started, for
            example while the agent boots. Wait with a background `sleep 60` and return to step 1;
            after three such returns, report that the lane did not start instead of waiting more.
        - Otherwise, such as `reason` `timeout` while `working`, the lane still works; return to
            step 1. Never send the brief again.
- **Read**: `hc read <address> --lines 200` prints the screen and its history as text; the reply is
    the agent's last message, which ends with `LANE-READY` or `LANE-BLOCKED` for a lane. If the
    output starts inside the reply, read again with more lines; never report an older message as the
    reply. `hc get <address> --json` gives the state, `status`, and `turn`.
- **Prompt**, such as continuing a lane after `LANE-BLOCKED`: record `turn` from
    `hc get <address> --json`, run `hc send <address> "<literal message>"`, and Wait as above. A send
    to a blocked lane fails with exit code 9; leave that to the user and do not force it.
- **Close**: after `hc get <address> --json` confirms that the terminal is the lane's, run
    `hc kill <address>` and then `hc rm <address>`, each as its own call.
- **Clean up**: after the user merges, run `cleanup_worktrees.py` by its absolute path with the home
    directory expanded, as shown in the rendered `excludedCommands` entry; `--dry-run` previews. It
    removes a lane worktree under `~/.herdr/worktrees` when a merged pull request's head is the
    branch tip and the tree is clean, and closes the Herdr workspaces this session created for it.
    Do not remove lane worktrees by hand with `herdr worktree remove`.
