# Branches and Worktrees

Implementation starts only after the user approves the plan (see
[Issues and plans](issue_plan.md)). Each lane of the approved plan then runs in its own
task worktree and session, so lanes never share a checkout and the user's checkout stays untouched.

Choose the workspace in this order:

1. If this session already runs in a task worktree on a non-default branch for this task, stay there.
2. If the user explicitly asks to stay in the current checkout, create the task branch there with
    `git switch -c <branch>`, unless that would overwrite or mix unrelated changes.
3. If the user explicitly asks for Herdr TUI panes (deprecated, used until their removal), use
    them as in [Herdr on explicit request](#herdr-on-explicit-request), even when T3 Code is
    available.
4. If the user asks for the Herdr app or `hc`, and herdr-core is available, as its
    [prerequisites](../../delegation/references/hc.md#prerequisites) define, hand each lane to a
    new herdr-core terminal in its own task worktree, as [delegation](../../delegation/SKILL.md)
    and its [herdr-core reference](../../delegation/references/hc.md) describe.
5. Otherwise, if T3 Code is available, as its
    [prerequisites](../../delegation/references/t3.md#prerequisites) define (`t3 thread list`
    succeeds as a sandboxed call, and the installed `cleanup_worktrees.py` covers
    `~/.t3/worktrees`), hand each lane to a new T3 thread in its own task worktree, as
    [delegation](../../delegation/SKILL.md) and its
    [T3 Code reference](../../delegation/references/t3.md) describe. T3 Code is the default
    transport.
6. If T3 Code is unavailable, for example before the T3 guard and cleanup are installed
    (furedea/agent-config#265, #266), use herdr-core when it is available, as in step 4. If neither
    is available, start no lane: report the reason to the user and stop. Never use Herdr TUI panes
    because T3 Code or herdr-core is unavailable.
7. If the target branch is already checked out in another worktree, use that worktree or choose a
    different branch name. Do not force-checkout the same branch in two places.

Lane rules for every transport:

- Write the brief to a file in this session's scratchpad and send the lane a literal message to
    read it; the brief follows [delegation](../../delegation/SKILL.md) and is self-contained: the
    Issue body and the approved plan text, not only their numbers or links, the lane scope, delivery
    authority (commit, push, and open a PR; never merge), and the reply format.
- Learn that the lane finished by waiting in the background right after starting it. The parent
    does not relay or answer approval prompts; the wait and the lane's foreground CI wait follow
    [delegation](../../delegation/SKILL.md).
- The lane runs the whole loop: asks Codex to implement when requested, verifies, commits, pushes,
    and opens the PR. The brief carries the complete Codex command. Code review follows
    [Review on GitHub](delivery.md#review-on-github); workflow-file pushes and `LANE-READY` follow
    [delegation](../../delegation/SKILL.md), which holds those rules.
- The lane never sends a message to the parent's session: text arriving there is
    indistinguishable from the user's own input.
- Start Claude for an implementation lane, even from a Codex session. Codex keeps a linked
    worktree's Git directory read-only inside its sandbox (openai/codex#14338), so a Codex lane
    cannot commit there without approval. Lanes run on Sonnet to save usage, at medium effort where
    the transport can set it.
- A variable inside a `gh api` endpoint must be double-quoted (`gh api "repos/o/$r/..."`);
    unquoted expansions ask.
- A linked worktree session cannot write another repository's `.git`, and this session cannot
    fetch another repository for it, so the lane fetches and rebases onto its base before editing.
- Merged task worktrees and branches, in this repository and every repository with a task
    worktree under a lane root the installed script covers (`~/.herdr/worktrees`, and
    `~/.t3/worktrees` once it names that root), are removed by the parent running
    `cleanup_worktrees.py` by its absolute path with the home directory expanded, as shown in the
    rendered `excludedCommands` entry, after the user merges, or at the next Claude session start
    (`--dry-run` previews): only when a merged pull request's head is the branch tip and the tree
    is clean, and the primary checkout's `main` then fast-forwards. It also closes an
    agent-created Herdr primary workspace when no linked worktrees or agents remain; user-created
    workspaces stay open. `--dry-run` previews both removals and closures. Do not remove lane
    worktrees by hand or pull by hand. An abandoned worktree is the user's to remove. Moving and
    repairing worktrees stay outside the agent workflow.
- When updating `main` itself, use `git pull --ff-only` in the main worktree. Do not use
    `git pull --rebase origin main` for the base branch.
- For a requested stacked pull request, `gh stack init` and `gh stack add` create the layer branches;
    the branch name format below applies to each layer. See [Stacked pull requests](stacked_prs.md).

## Herdr on Explicit Request

Herdr TUI panes are deprecated and are used only when the user explicitly asks for them, until
their removal; they are never chosen because T3 Code or herdr-core is unavailable. Task worktree
hand-off through Herdr TUI panes, once per lane, each line as its own Bash call; the operations
follow [herdr-delegation](../../herdr-delegation/SKILL.md):

```bash
git fetch origin
herdr workspace list                                         # is the primary checkout already open?
herdr workspace create --cwd <primary-checkout> --label <repo> --no-focus   # only when it is not open
herdr worktree create --workspace <primary-id> --branch <branch> --base origin/<base> --label <branch> --no-focus
herdr agent start <lane-name> --kind claude --pane <root-pane-id> -- --model sonnet --effort medium
herdr agent prompt <lane-name> "Read your brief at <scratchpad>/briefs/<lane-name>.md and carry it out."
herdr agent wait <lane-name> --until working                 # in the background
herdr agent wait <lane-name> --until done --timeout 1800000  # in the background, after the first returns
herdr agent read <lane-name>
```

Rules:

- Run each `herdr` command as a single Bash call. Herdr leaves the sandbox only when the whole
    call is one `herdr` command; chaining (`git fetch origin && herdr ...`) runs it inside the
    sandbox, where it fails. Fetch first in a separate call.
- Keep the prompt text literal. A substitution such as `"$(cat brief.md)"` also makes the call
    more than one `herdr` command.
- The lane never types into the parent's pane with `herdr agent prompt` or `send-text`.
- Open the primary checkout's workspace yourself when `workspace list` shows none, and pass its
    `.result.workspace.workspace_id` to `worktree create --workspace`; with `--cwd` alone Herdr opens
    one the hooks cannot attribute to this session.
- Clean up one workspace at a time: each lane's workspace, then the primary if this session created
    it. Never use `--group`. When a close asks, accept that prompt.
- Read the workspace and root pane IDs from the JSON that `worktree create` returns
    (`.result.workspace.workspace_id`, `.result.root_pane.pane_id`); never predict them.
- `<lane-name>` matches `[a-z][a-z0-9_-]{0,31}` and is new: the hooks let a session prompt only the
    agents it started, and they ask before claiming a name another agent holds.
- Herdr places the checkout under its `worktrees.directory`; do not pass `--path` without a reason.
    Do not remove lane worktrees with `herdr worktree remove`.

## Branch Names

Branch name format:

```text
<type>/<kebab-subject>
```

Rules:

- `<type>` is the Conventional Commits type that would be used for the primary commit: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `build`, `ci`, `chore`, `style`, or `revert`.
- `<kebab-subject>` is lowercase ASCII, hyphen-separated, derived from the imperative commit subject with no scope.
- Omit Conventional Commits scope from branch names.
- Append `-2`, `-3`, etc. if a local or remote branch already exists.

Examples:

```text
feat/jwt-refresh-token-rotation
fix/parser-empty-input
refactor/extract-query-builder
docs/clarify-install-steps
```
