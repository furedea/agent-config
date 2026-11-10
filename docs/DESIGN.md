# Design

<p align="center">
  <a href="DESIGN.md"><img alt="English" src="https://img.shields.io/badge/lang-English-0969da"></a>
  <a href="DESIGN_ja.md"><img alt="日本語" src="https://img.shields.io/badge/lang-%E6%97%A5%E6%9C%AC%E8%AA%9E-8c959f"></a>
</p>

How work flows from a request to a merged pull request, which session owns each step, which skill
the agent follows there, and how the hooks verify and police the work. Decisions and their reasons
live in [`docs/adr/`](adr/).

## Development Cycle

The cycle is the same wherever the session is opened.

```mermaid
flowchart LR
  P[Parent: Issue and plan] --> A{User approves}
  A --> L[Parent: open lanes]
  L --> I[Lane: Codex implements]
  I --> V[Lane: verify, commit, PR]
  V --> RV[GitHub: claude-review and codex-review]
  RV -->|findings, lane fixes and pushes| RV
  RV --> R[Lane: LANE-READY]
  R --> W[Parent: check and report]
  W --> M[User merges]
  M --> C[Parent: clean up]
```

| Step                  | Owner         | Starts                                                                                                                                                                                                                       | Skills                                                         |
| --------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| 1. Issue and plan     | Parent        | —                                                                                                                                                                                                                            | `issue-workflow`                                               |
| 2. Approve            | User          | —                                                                                                                                                                                                                            | —                                                              |
| 3. Open lanes         | Parent        | a Herdr worktree and a Sonnet lane at medium effort per lane, with a brief                                                                                                                                                   | `git-workflow` (branches), `herdr-delegation`                  |
| 4. Implement          | Lane          | Codex (tests first, no commits)                                                                                                                                                                                              | `tsdd`, the language style skills, `domain-modeling`           |
| 5. Verify and deliver | Lane          | —                                                                                                                                                                                                                            | `git-workflow` (commits, delivery)                             |
| 6. Review and fix     | Lane          | the GitHub `claude-review` and `codex-review` checks; the lane fixes every finding                                                                                                                                           | `git-workflow` (delivery), `herdr-delegation`                  |
| 7. Report             | Lane → Parent | the lane ends with `LANE-READY`; the parent waits with `herdr agent wait` and reads it                                                                                                                                       | `herdr-delegation`                                             |
| 8. Check and report   | Parent        | —                                                                                                                                                                                                                            | —                                                              |
| 9. Merge              | User          | —                                                                                                                                                                                                                            | —                                                              |
| 10. Clean up          | Parent        | after the user merges: run `cleanup_worktrees.py` by its absolute path with the home directory expanded, as shown in the rendered `excludedCommands` entry; never remove lane worktrees by hand with `herdr worktree remove` | `git-workflow` (branches), `issue-workflow`, `source-of-truth` |

| Who                   | Does                                                                            | Never does                                              |
| --------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------- |
| User                  | approves plans, merges, pushes workflow files, deletes or archives repositories | —                                                       |
| Parent session (Opus) | Issues, plans, lanes, final check, cleanup                                      | edits files, merges                                     |
| Lane (Sonnet)         | runs Codex, verifies, commits, opens PRs, fixes review findings                 | writes the implementation, types into the parent's pane |
| Codex                 | implements                                                                      | commits or pushes (it cannot write `.git`)              |

The lane reports by ending its last message with `LANE-READY`, and the parent reads it. The lane
never types into the parent's pane, because the parent cannot tell that text from the user's.

Caution: the sandbox limits where an agent writes, not what you later run outside it, so run agent
changes only after they are reviewed and merged.

Caution: do not open a session in the home directory, because the sandbox lets a session write
everywhere under its working directory.

### Constraints

- The parent cannot write another repository's `.git`; lanes fetch, commit, and push there.
- No session writes any repository's `.git/hooks` or `.git/config`, so lanes push without `-u`.
- Run each `herdr` command and each Codex plugin call as one command: no `cd`, pipe, redirect, or `$`.
- Codex cannot reach the network or the Nix daemon; the lane updates dependencies and computes Nix hashes.
- The agent's GitHub App cannot push workflow files; the user pushes them.
- Dependencies younger than seven days are not installed (pnpm `minimumReleaseAge`, uv `exclude-newer`).

## Verification

Native provider lifecycle hooks register the session's worktree and verify changes automatically;
see [ADR-0003](adr/0003_register_verification_in_native_hooks.md).

- State lives under
  `${XDG_STATE_HOME:-~/.local/state}/agent-harness/verification/<worktree>/<session>/`.
  `results.json` there identifies the provider session and its latest check results.
- To verify a recorded session again, run
  `~/.claude/hooks/verification_session.py verify <session-directory>`. Add `--force` to rerun
  checks whose receipts are still valid. `status <session-directory>` prints the record.
- Ended or inactive records expire after seven days. Failure logs are capped at 1 MiB each and
  100 MiB in total.
- Each check may run for 300 seconds. `RUN_RELATED_TESTS_TIMEOUT_SECONDS` overrides that budget
  when it is set explicitly.
- A check's tool is looked up on the agent's `PATH` first. When it is absent and the project's
  `flake.nix` declares a dev shell, the check runs as `nix develop --no-write-lock-file --command ...` (it never writes `flake.lock`) under the same
  timeout and logs. A tool that neither `PATH` nor a dev shell provides is reported as
  `Verification unavailable`; it is not a failure and does not block Stop, but it is not a pass
  and `verify` still exits non-zero. Such a result is retried on every pass instead of reused,
  and a budget spent before the dev shell came up is reported the same way. A project that
  declares a dev shell is expected to enter it, so nix failing before the shell starts (for
  example an evaluation error in a `flake.nix` edited this session) is a failure that blocks
  Stop, with nix's output in the log. That failure is recorded as `dev_shell_failed` and, like
  `missing_tool`, is rerun on every verification instead of reused: a broken `flake.nix` blocks
  every time because nix fails fast, while a transient nix problem clears on the next Stop
  without `verify --force`.

## Hook Decisions

- Denials are reserved for deny prefixes, forbidden patterns, dangerous Git operations, secret
  policies, and missing verification registration.
- A command inside an approved family whose form the precise rules do not list, a command the
  static inspection cannot decode, or a tool target outside both the worktree and the session temp
  directories is escalated to the provider's permission prompt instead; see
  [ADR-0006](adr/0006_escalate_unrecognized_command_forms_to_the_provider_prompt.md).
- Commands whose effects the sandbox contains, such as script execution, in-place edits, and
  read-only inspection with any argument, run without a prompt. Only effects that escape the
  sandbox or cannot be undone ask; see
  [ADR-0007](adr/0007_ask_only_for_effects_that_escape_the_sandbox.md), refined by
  [ADR-0009](adr/0009_review_only_commands_that_reach_past_the_sandbox.md).
- Docker runs outside the sandbox, so only its read-only inspection forms run without a prompt and
  every other form asks; see
  [ADR-0017](adr/0017_ask_for_every_docker_form_the_allowlist_does_not_list.md).
- `agent-browser` and `agent-desktop` run outside the sandbox, and their listed forms run without
  a prompt. `file:` and `chrome:` URLs, and terminals, System Settings, and credential apps, are
  denied, and forms that reach logged-in sessions or unnamed targets ask; see
  [ADR-0018](adr/0018_allow_browser_and_desktop_automation_except_named_risky_forms.md). Each
  subcommand may use only the options listed for it, and its arguments must resolve, through
  symlinks, inside the worktree or the session's temporary directory, or the call asks, and so
  does every file the browser daemon writes but a bare screenshot; see
  [ADR-0019](adr/0019_resolve_automation_path_arguments_through_symlinks.md).
- The supplementary guards judge only statically determinable shell text and ask for the rest; see
  [ADR-0015](adr/0015_judge_only_statically_determinable_shell_text_in_the_guards.md) and
  [ADR-0016](adr/0016_inspect_shell_syntax_in_the_supplementary_command_guards.md).
