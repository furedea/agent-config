---
status: proposed
date: 2026-11-10
amended:
  - "2026-11-11: the hook behaviour, the two reviews, the Keychain"
  - "2026-11-15: static rules block on edit; suppression; shared rules only in trusted repositories"
---

# ADR-0021: Enforce prose rules with each tool's own checks that report before they block

In the context of turning the prose rules of `AGENTS.md` and the style skills into machine checks (#74), facing rules
that differ in how they can be judged (existing linter, ast-grep, model, prose only) and a model judge whose cutoffs
are not yet fitted (ADR-0020), we decided for making each tool's own configuration the single source of truth (linter
config, ast-grep rule YAML with its native tests, jev-lint rule files), deleting a prose rule in the same change that
replaces it with a check (a model-judged rule keeps its prose until it is promoted), blocking every edit that leaves a
static (ast-grep) finding of severity error, with no advisory tier for static rules, running the shared static rules
only in repositories of trusted owners, leaving a real exception to a suppression comment that only the user approves, showing model-judged findings to the agent by blocking Stop once for each set of inputs and never blocking again on the same inputs, promoting a model-judged rule to a gate that blocks every time only after
its example tests show no false positive, running model-judged rules once at Stop as `jev-lint review` over the changed functions of trusted
repositories, reusing `jev-lint`'s own verdict cache stored outside the repository, and building and pinning `jev-lint` with its dependencies through Nix as `packages.<system>.jev-lint` in this
repository (agent-config), and against a separate rule registry, advisory static rules, blocking on edit for model-judged rules, judging per edit, and running without a cache,
to achieve one place per rule and no prose that can drift from its check, accepting that a static rule with a false
positive stops the agent until the rule is fixed or deleted or the user approves a suppression, that an unpromoted model-judged rule can be
ignored by the agent after it has seen the finding once, that a Stop block delays the end of a turn once per change, that an unpromoted model-judged rule exists both as prose and as a check until its promotion, that a Stop-time verdict arrives after the edits it judges, that there is no single inventory
of rules across tools, that the hook depends on `jev-lint`'s cache and batching behaviour, and that only the owner's
own repositories get model judgement and the shared static rules.

## Decisions

- **Source of truth.** Each rule lives only in the configuration of the tool that judges it: `pyproject.toml`,
    `Cargo.toml`, `.golangci.yml`, or `.oxlintrc.json` for existing linters; ast-grep rule YAML with ast-grep's own
    tests (`sgconfig.yml`, rule tests) for structural rules; jev-lint's own rule files for model-judged rules. A rule
    that no tool can judge stays as prose.
- **Prose is deleted, not kept.** The change that replaces a prose rule with a check deletes that rule from
    `AGENTS.md` or the style skill in the same PR, so no second statement of the rule remains to drift. The one
    exception is a model-judged rule that has not been promoted: its check is advisory and unfitted, so its prose stays
    until the promotion change, which then deletes it. The
    prose-to-check mapping (original text, location, tool, tests) is recorded in that PR's body only, not in the
    repository.
- **Static rules block.** A static (ast-grep) rule is either on, with `severity: error`, or deleted; there is no
    advisory tier and no advisory-then-promote path for static rules. An edit that leaves an error finding is
    blocked after the edit (`decision: block` with the findings as the reason), like a linter error, so the agent
    fixes it before it goes on. A rule that cannot meet that bar is not added. Findings of a lower severity and a
    scanner that fails, with any findings it printed before failing, are still only feedback, so a broken or
    timed-out scan cannot trap the agent. A scan that finished and reported errors through its exit status blocks
    even when its output was cut before the error records, so a large output cannot hide them. A rule is set to error only
    after its hits in the owner's repositories have been audited (#190–#195, #202). Every error rule carries a
    `note` with the exact fix, which the rule tests require; the block shows each finding's rule, location, message
    and fix, then tells the agent once to fix the code as shown and not to move or split it to avoid the rule.
- **Whose style.** The shared rules shipped with the hooks are the owner's style, so they run only in repositories
    whose origin owner `trusted_owners` trusts, as model rules do. In any other repository they do not run at all:
    that project's own style takes precedence, and blocking there would make the agent rewrite code it was not
    asked to touch or ask for suppressions in someone else's codebase. Rules from a project's own `sgconfig.yml`
    run everywhere.
- **Suppression.** A rare real exception is suppressed at the site with an `ast-grep-ignore` comment that names the
    rule and states the reason. Whether the exception is real is the user's judgment: the suppression guard asks the
    user for every edit that adds such a comment, changes the rules one names, or may give a first-line marker the
    whole file, as it does for the other lint suppressions including Go's `//nolint`, and the agent never adds one
    on its own. The guard runs before edits in every provider. Claude Code asks; the others cannot ask, so a new
    suppression is denied there and the user adds the exception.
- **Hook behaviour.** A model-judged finding
    at Stop follows the rule that the verification receipts already use: findings on inputs not judged before block
    Stop once (`decision: block` with the findings as the reason), so that the agent sees them, because the only
    non-blocking Stop output, `systemMessage`, reaches the user and not the agent. The same findings on unchanged
    inputs are only a message (`unchanged; not rerun`) and never block again, so a finding the agent declines to
    fix cannot trap it; nothing blocks while `stop_hook_active` is set, and findings that it kept from blocking are recorded as not yet shown, so that they block once at the next Stop on the same inputs; and anything that prevents a run is only a
    message. A model-judged rule becomes a gate that blocks every time only when its example tests pass with no false positive on
    the conforming examples and on the repository's own files; the promotion is a reviewed change to the tool's
    config. Model-judged rules are not promoted until their cutoff has been fitted on a larger corpus, as ADR-0020
    requires.
- **Judging time.** Static rules run on the files changed by each edit. Model-judged rules run at Stop, as
    `jev-lint review --json` with all model rules (`-R <rules dir>`) over the changes made in the session, not per
    edit and not once per rule and file. `jev-lint review` has no mode for the session's changes as a whole:
    `--base <commit>` judges the commits since that commit (`base...HEAD`) and, without it, the working tree against
    `HEAD` plus the files git does not track yet. The hook therefore runs up to two reviews, which share the subject
    cap and the verdict cache: one with `--base` set to the commit `HEAD` pointed to when the session started, which
    the hook records at session start, so that functions committed during the session are still judged (it is skipped
    when nothing was committed or the record has no start commit), and one without it for the changes not committed
    yet, limited to the files whose content differs from the session's baseline snapshot, so that edits and untracked
    files that were already there and that the session never touched are not sent. A file the session did touch is
    judged by its whole diff against `HEAD`, so earlier uncommitted hunks in it are judged too; that over-inclusion
    is accepted because the baseline records signatures per file, not per hunk. A
    function that was committed and then edited again can appear in both; its finding is reported once.
- **Subjects and context.** `jev-lint` selects the subjects with each rule's ast-grep matcher and judges per function
    (the rule's `subject:`). Each subject is judged with the function plus the same file's imports and enclosing
    declarations (state arm `local`); no other file is sent. Only functions changed in the session are judged, at most
    250 per Stop, and the hook reports how many were skipped. The value comes from measurement: over this
    repository's merged PRs, `jev-lint review --dry-run` planned at most 104 subjects in 10 requests (about 0.0025
    USD), and 30 recorded Stop runs took 2.7 to 7.9 seconds for 1 to 8 requests, because requests run concurrently
    and wall time follows the request count, not the subject count. 250 holds twice the largest measured session
    whole, costs about 0.006 USD per Stop at the cap, and leaves the 90-second Stop budget a wide margin.
- **Cache.** The hook does not keep a cache of its own. It passes `jev-lint` its verdict cache (`-c <path>`) stored
    outside the repository, under the agent state directory, because `jev-lint` documents the cache as trusted input
    that can silence rules, and a file inside the repository could be committed. Keeping it under the state directory
    means it is not committed; it does not by itself stop the agent from writing there. The hook change therefore adds
    a rule to `secret_path_policy.json` that refuses any tool call naming the cache path, with a test. The guard
    sees only paths that a call names literally: a command that builds the path at run time, or a program that
    writes it, is not covered, and the sandbox allows writes under the state directory, so the cache is protected
    against accident and casual edits and not against a determined agent. The file is shared by every
    repository, worktree, and session, and `jev-lint`'s write atomicity is not verified, so the hook serializes runs
    with a lock file next to the cache and gives up with a one-line notice if it cannot take the lock within the run's
    time limit. A `jev-lint` or model change is
    handled by `jev-lint`'s own cache keying.
- **Where it runs.** The Stop-time run is part of the existing Stop flow of agent-config's hooks (Python), not a
    second Stop hook: `verification_session` calls it after the verification passes and it reuses the verification's
    receipts, so that one place decides when a result is new and when it is unchanged, and `trusted_owners`. A
    separate hook would run in parallel with the verification, could not apply the unchanged-inputs rule to both, and
    could not tell the agent anything without a second block. agent-harness holds no
    model-rule logic: it only distributes configuration, while `jev-lint` is a tool that this hook runs, like
    ast-grep. The Rust `JudgementBackend` of agent-harness #209 is removed as dead code.
- **Repository gate.** Code is sent to the model only for repositories whose owner `trusted_owners` trusts (the
    owner's own repositories). For any other repository the hook skips model rules and says so in one line. An
    environment variable (`AGENT_MODEL_RULES=off`) switches model rules off entirely.
- **Key handling.** The hook runs `op run --environment <id> -- jev-lint review --json --no-config --fail-on error
    -R <rules dir> -c <state dir>/agent-harness/model-rules/verdicts.json` (with `--base <commit>` for the review of
    commits). `--no-config` keeps a repository's `.jev-lint.yaml` from changing the endpoint the code is sent to.
    The key comes from the "jev" 1Password Environment, is injected only into the `jev-lint` child process, and is
    never read, printed, or logged by the hook. The Environment ID and the token are both read from the macOS login
    Keychain as generic passwords of the current user (services `agent-model-rules-op-environment` and
    `agent-model-rules-op-token`); the ID is not a UUID, so it is checked only as lowercase letters and digits. `op`
    runs with a 1Password service account, so that no interactive approval is needed at every Stop. The account's
    token is read-only and limited to the "jev" Environment and a dedicated automation vault. The hook passes the
    token as `OP_SERVICE_ACCOUNT_TOKEN` only to the `op` child process, never to the agent, and to `jev-lint` only
    through what `op` injects. Child processes get only an allowlist of environment variables, so a variable such as
    `TYPESAFE_BASE_URL` cannot redirect the request, and their standard error is discarded.
- **Failure behaviour.** A run has 60 seconds and never ends in a block for a reason other than a finding. When it
    is skipped (untrusted repository, kill switch, missing Keychain item, missing `op` or `jev-lint`) or fails
    (timeout, non-zero exit, unparsable output, errors reported by `jev-lint`), the hook returns a one-line message
    instead of staying silent, and does not store a receipt, so the next Stop tries again.
- **Orphaned children.** When Claude Code kills the hook (its timeout, Ctrl+C, closing the session), the hook cannot
    clean up, and macOS has no parent-death signal, so `op` and `jev-lint` could run on. Each child is therefore
    started under `/usr/bin/timeout -s TERM -k 5 <budget>`, which ends it at its own deadline whatever happens to
    the hook; the hook's process-group kill stays as a backstop a second after. The program is named by absolute
    path, so nothing on `PATH` can stand in for it: macOS ships a BSD `timeout` there and Linux a GNU one. Only what
    both accept is used (short options, a plain number of seconds with decimals; the BSD one rejects `--version` and
    needs no probe). When `/usr/bin/timeout` does not exist the hook falls back, silently, to its own kill alone, and
    a killed hook then leaves the child until it ends by itself. A child is bounded by its budget (at most 60 seconds)
    plus the 5-second kill-after. The hook reads an exit status of 124 (deadline), 137 (GNU, after the kill) or
    -9 (BSD `timeout` is itself in the process group it kills, so it dies of the signal) as a timeout. Measured on
    macOS with the BSD `timeout`: a child that takes `TERM` ended 2.00 seconds after its hook was killed with a 2-second
    budget, and one that ignores `TERM` 2.96 seconds after with `-k 1`.
- **First rules.** Each is a `jev-lint` rule file (an ast-grep rule plus `ask:`): command/query naming of functions
    (M-05), error messages that name the operation and subject (M-21), and known-defect markers (`xfail`,
    `test.fails`) that carry a comment naming the removal condition (M-60). Their prose is kept until the rule is
    promoted, as stated in the prose decision above.
- **Backend.** `jev-lint` is built and pinned with all its dependencies through Nix as `packages.<system>.jev-lint`
    in this repository's flake, and dotfiles installs it from agent-config. It is never fetched with `npx` at run
    time, and the hook runs the `jev-lint` command directly, so replacing it later, as ADR-0020's conditions allow,
    means changing this hook. This replaces two parts of ADR-0020: its run mode (`npx` over a Nix-provided Node,
    whose transitive dependencies were not pinned) and its judgement backend abstraction, which is dropped because
    nothing else implements it and the hook is the only caller. ADR-0020's choice of `jev-lint` stands, and both ADRs
    are still Proposed. Model-judged rules are never
    skipped silently: a skip or failure is reported as in Failure behaviour.

## Which rules ast-grep may block

A blocking ast-grep rule must judge one construct, locally and reliably. A rule that needs any of the following goes to
the language's own linter, compiler, or test runner when one can judge it, and otherwise to `jev-lint` only if the
function, its file's imports, and its enclosing declarations (all that `jev-lint` is given) are enough. A rule that no
tool can judge with the context it has stays as prose:

1. Information outside the file: configuration, `conftest.py`, other modules.
2. Data flow or execution order: values passed through assignments, scopes, or a class hierarchy.
3. Parsing a nested grammar or expression with a regular expression: boolean `cfg(...)` predicates, escape sequences,
    quoting. Matching a fixed name, or a literal prefix of one string or attribute path, is a local check and may
    block: `go_error_no_failed_to_prefix` (the literal prefix of one error string) stays. The `cfg_attr` branch of
    `rs_no_mocking_library` parses a nested attribute with a regular expression, so it falls under this type and is a
    candidate to narrow or move (#196).
4. Many equivalent spellings that a rule cannot list completely: YAML quoting, flow and block forms, import aliases
    combined with other cases. A rule that only detects a short, closed list of spellings of one name, such as the
    aliases of one import, may still block.

The evidence is the review of PRs #192-#195. The rules below were removed or demoted to `jev-lint` after drawing 8 to 34
review threads each without converging, and each needs one or more of the cases above. The rules that stayed as
blocking ast-grep rules, which judge one local construct, drew 7 or fewer threads (3 to 7 for the Bash and GitHub
Actions rules of #194, whose misses were sent to #196 instead of being patched). The types are the numbers above.
Thread counts are those in the "ast-grep から外した規則と理由" tables of the merged PR bodies of #192, #193, #194,
and #195.

| Rule                                     | Threads | Type    | Destination                                             |
| ---------------------------------------- | ------- | ------- | ------------------------------------------------------- |
| `py_async_test_anyio_marker` (#192)      | 34      | 1, 4    | pytest itself (fails an async test no plugin runs)      |
| `ts_no_unvalidated_json_cast` (#195)     | 26      | 1, 4    | oxlint `no-unsafe-type-assertion` and related rules     |
| `rs_unit_test_in_test_module` (#193)     | 21      | 1, 3, 4 | clippy `tests_outside_test_module`                      |
| `py_pydantic_validate_json` (#192)       | 17      | 2, 4    | `jev-lint` `json-parse-uses-model-validate-json`        |
| `gha_workflow_default_shell` (#194)      | 15      | 2, 3, 4 | `jev-lint` `workflow-default-shell`                     |
| `gha_workflow_concurrency` (#194)        | 12      | 3, 4    | `jev-lint` `workflow-concurrency`                       |
| `ts_no_other_test_framework` (#195)      | 12      | 2       | oxlint `no-restricted-globals`, `no-restricted-imports` |
| `py_plain_class_slots` (#192)            | 11      | 2, 4    | `jev-lint` `plain-class-defines-slots`                  |
| `bash_strict_mode_header` (#194)         | 11      | 2, 3, 4 | `jev-lint` `strict-mode-header`                         |
| `ts_catch_rethrow_requires_cause` (#195) | 11      | 2, 4    | oxlint `preserve-caught-error`                          |
| `py_frozen_base_model_config` (#192)     | 8       | 2, 4    | `jev-lint` `frozen-base-model-sets-all-settings`        |
| `rs_no_path_from_format` (#193)          | 8       | 3, 4    | `jev-lint` `paths-are-joined-not-formatted`             |

Rules with fewer threads that were also removed (for example `py_frozen_base_model_no_override`, `rs_no_get_prefix`,
`rs_fs_call_needs_context`) are listed in the same PR bodies; they fall under the same cases.

## Alternatives considered

- **A rule registry (one YAML file per rule with source link, method, threshold, and examples).** Rejected: it
    duplicates what each tool's config already declares, and its source links are unnecessary once the prose rule is
    deleted.
- **Findings that never block, as `systemMessage` only.** Rejected: that output reaches the user and not the agent,
    so the agent would never see a finding unless the user relayed it.
- **Block at every Stop that has findings.** Rejected: an agent that declines a finding would be stopped again on
    the same inputs; blocking only for inputs not judged before, as the verification receipts do, cannot loop.
- **A second Stop hook for the model rules.** Rejected: see Where it runs.
- **Block on edit for model-judged rules.** Rejected: the model judge is not yet precise enough (ADR-0020), and a
    false positive would stop the agent on every edit.
- **Advisory static rules, promoted to blocking after their tests pass.** Rejected (amended 2026-11-15): an advisory
    finding after an edit is easy for the agent to ignore, so the rule does not hold, and a second tier keeps rules
    that are not trusted enough to block. A structural rule's precision can be checked before it is added, so a rule
    that cannot block is deleted instead.
- **Judge per edit.** Rejected: cost and latency grow with every edit, and most intermediate states are rewritten
    before they matter.
- **No cache.** Rejected: Stop fires more than once in a session, and each firing would
    re-judge units that did not change since the previous one.
- **A harness-side cache keyed by rule, `jev-lint` version, model, and unit hash.** Rejected: `jev-lint` already caches verdicts
    and batches subjects per file, so a second cache would duplicate it and could disagree with it.
- **One `jev-lint run` call per rule and file.** Rejected: it forgoes `jev-lint`'s batching of up to 256 subjects per
    file and its subject selection, and multiplies process starts and model calls.
- **Running `op` as the signed-in user.** Rejected: 1Password asks for approval at every Stop after a period of
    inactivity, which interrupts the user for an advisory check; a read-only service account avoids the prompt.
- **Keeping the cache inside the repository.** Rejected: `jev-lint` treats the cache as trusted input that can silence
    rules, so it must not live where a commit can alter it. Protecting it from agent writes is the guard rule of the Cache decision, which applies to the chosen location as well.

Revisit when false-positive reports after promotion show that the example tests are not a sufficient criterion, when
the lack of a cross-tool inventory hides rules that are still prose or duplicated, when Stop-time findings are mostly
ignored or arrive too late to act on, when `jev-lint`'s cache hit rate is too low to repay the model cost, or when the replacement
conditions of ADR-0020 are met.
