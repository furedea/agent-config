# ADR-0021: Enforce prose rules with each tool's own checks that report before they block

- Status: Proposed
- Date: 2026-11-10
- Amended: 2026-11-11 (the hook behaviour, the two reviews, the Keychain)

In the context of turning the prose rules of `AGENTS.md` and the style skills into machine checks (#74), facing rules
that differ in how they can be judged (existing linter, ast-grep, model, prose only) and a model judge whose cutoffs
are not yet fitted (ADR-0020), we decided for making each tool's own configuration the single source of truth (linter
config, ast-grep rule YAML with its native tests, jev-lint rule files), deleting a prose rule in the same change that
replaces it with a check (a model-judged rule keeps its prose until it is promoted), showing findings to the agent by blocking Stop once for each set of inputs and never blocking again on the same inputs, promoting a rule to a gate that blocks every time only after
its example tests show no false positive, running model-judged rules once at Stop as `jev-lint review` over the changed functions of trusted
repositories, reusing `jev-lint`'s own verdict cache stored outside the repository, and building and pinning `jev-lint` with its dependencies through Nix as `packages.<system>.jev-lint` in this
repository (agent-config), and against a separate rule registry, blocking on edit, judging per edit, and running without a cache,
to achieve one place per rule and no prose that can drift from its check, accepting that an unpromoted rule can be
ignored by the agent after it has seen the finding once, that a Stop block delays the end of a turn once per change, that an unpromoted model-judged rule exists both as prose and as a check until its promotion, that a Stop-time verdict arrives after the edits it judges, that there is no single inventory
of rules across tools, that the hook depends on `jev-lint`'s cache and batching behaviour, and that only the owner's
own repositories get model judgement.

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
- **Hook behaviour.** Static rules return findings as feedback after an edit and never block. A model-judged finding
    at Stop follows the rule that the verification receipts already use: findings on inputs not judged before block
    Stop once (`decision: block` with the findings as the reason), so that the agent sees them, because the only
    non-blocking Stop output, `systemMessage`, reaches the user and not the agent. The same findings on unchanged
    inputs are only a message (`unchanged; not rerun`) and never block again, so a finding the agent declines to
    fix cannot trap it; nothing blocks while `stop_hook_active` is set, and findings that it kept from blocking are recorded as not yet shown, so that they block once at the next Stop on the same inputs; and anything that prevents a run is only a
    message. A rule becomes a gate that blocks every time only when its example tests pass with no false positive on
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
    yet. Edits that were already uncommitted when the session started are in the second review and are judged too;
    that over-inclusion is accepted because the hook cannot tell them apart without a working-tree snapshot. A
    function that was committed and then edited again can appear in both; its finding is reported once.
- **Subjects and context.** `jev-lint` selects the subjects with each rule's ast-grep matcher and judges per function
    (the rule's `subject:`). Each subject is judged with the function plus the same file's imports and enclosing
    declarations (state arm `local`); no other file is sent. Only functions changed in the session are judged, at most
    20 per Stop at first, and the hook reports how many were skipped.
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

## Alternatives considered

- **A rule registry (one YAML file per rule with source link, method, threshold, and examples).** Rejected: it
    duplicates what each tool's config already declares, and its source links are unnecessary once the prose rule is
    deleted.
- **Findings that never block, as `systemMessage` only.** Rejected: that output reaches the user and not the agent,
    so the agent would never see a finding unless the user relayed it.
- **Block at every Stop that has findings.** Rejected: an agent that declines a finding would be stopped again on
    the same inputs; blocking only for inputs not judged before, as the verification receipts do, cannot loop.
- **A second Stop hook for the model rules.** Rejected: see Where it runs.
- **Block on edit.** Rejected: an unproven rule would stop the agent on false positives, and the model judge is
    not yet precise enough (ADR-0020).
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
