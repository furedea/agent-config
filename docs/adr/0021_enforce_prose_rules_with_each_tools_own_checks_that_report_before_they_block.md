# ADR-0021: Enforce prose rules with each tool's own checks that report before they block

- Status: Proposed
- Date: 2026-11-10

In the context of turning the prose rules of `AGENTS.md` and the style skills into machine checks (#74), facing rules
that differ in how they can be judged (existing linter, ast-grep, model, prose only) and a model judge whose cutoffs
are not yet fitted (ADR-0020), we decided for making each tool's own configuration the single source of truth (linter
config, ast-grep rule YAML with its native tests, jev-lint rule files), deleting a prose rule in the same change that
replaces it with a check, returning findings to the agent without blocking, promoting a rule to blocking only after
its example tests show no false positive, running model-judged rules once at Stop as a single `jev-lint review` over the changed functions of trusted
repositories, reusing `jev-lint`'s own verdict cache stored outside the repository, and pinning `jev-lint` with its dependencies through Nix behind the backend
abstraction, and against a separate rule registry, blocking on edit, judging per edit, and running without a cache,
to achieve one place per rule and no prose that can drift from its check, accepting that an unpromoted rule can be
ignored by the agent, that a Stop-time verdict arrives after the edits it judges, that there is no single inventory
of rules across tools, that the hook depends on `jev-lint`'s cache and batching behaviour, and that only the owner's
own repositories get model judgement.

## Decisions

- **Source of truth.** Each rule lives only in the configuration of the tool that judges it: `pyproject.toml`,
    `Cargo.toml`, `.golangci.yml`, or `.oxlintrc.json` for existing linters; ast-grep rule YAML with ast-grep's own
    tests (`sgconfig.yml`, rule tests) for structural rules; jev-lint's own rule files for model-judged rules. A rule
    that no tool can judge stays as prose.
- **Prose is deleted, not kept.** The change that replaces a prose rule with a check deletes that rule from
    `AGENTS.md` or the style skill in the same PR, so no second statement of the rule remains to drift. The
    prose-to-check mapping (original text, location, tool, tests) is recorded in that PR's body only, not in the
    repository.
- **Hook behaviour.** Findings are returned to the agent as feedback and never block. A rule becomes blocking only
    when its example tests pass with no false positive on the conforming examples and on the repository's own files;
    the promotion is a reviewed change to the tool's config. Model-judged rules are not promoted until their cutoff has
    been fitted on a larger corpus, as ADR-0020 requires.
- **Judging time.** Static rules run on the files changed by each edit. Model-judged rules run once at Stop, as a
    single `jev-lint review --json` over the session's uncommitted changes with all model rules (`-R <rules dir>`), not
    per edit and not once per rule and file.
- **Subjects and context.** `jev-lint` selects the subjects with each rule's ast-grep matcher and judges per function
    (the rule's `subject:`). Each subject is judged with the function plus the same file's imports and enclosing
    declarations (state arm `local`); no other file is sent. Only functions changed in the session are judged, at most
    20 per Stop at first, and the hook reports how many were skipped.
- **Cache.** The hook does not keep a cache of its own. It passes `jev-lint` its verdict cache (`-c <path>`) stored
    outside the repository, under the agent state directory, because `jev-lint` documents the cache as trusted input
    that can silence rules and a file inside the repository could be committed or edited by the agent. A backend
    or model change is handled by `jev-lint`'s own cache keying.
- **Repository gate.** Code is sent to the model only for repositories whose owner `trusted_owners` trusts (the
    owner's own repositories). For any other repository the hook skips model rules and says so in one line. An
    environment variable (`AGENT_MODEL_RULES=off`) switches model rules off entirely. The API key is never read, printed,
    or logged; the hook only checks that it is present.
- **First rules.** Each is a `jev-lint` rule file (an ast-grep rule plus `ask:`): command/query naming of functions
    (M-05), error messages that name the operation and subject (M-21), and known-defect markers (`xfail`,
    `test.fails`) that carry a comment naming the removal condition (M-60). Their prose is deleted when the rule is
    promoted, not before.
- **Backend.** `jev-lint` is pinned with all its dependencies through Nix and never fetched with `npx` at run time,
    and the hook calls it only through the backend interface, so that ADR-0020's replacement stays possible. This
    replaces only the run mode of ADR-0020 (`npx` over a Nix-provided Node, whose transitive dependencies were not
    pinned); ADR-0020's choice of `jev-lint` stands, and both ADRs are still Proposed. When no key is available,
    model-judged rules are reported as "N unjudged" and never skipped silently.

## Alternatives considered

- **A rule registry (one YAML file per rule with source link, method, threshold, and examples).** Rejected: it
    duplicates what each tool's config already declares, and its source links are unnecessary once the prose rule is
    deleted.
- **Block on edit.** Rejected: an unproven rule would stop the agent on false positives, and the model judge is
    not yet precise enough (ADR-0020).
- **Judge per edit.** Rejected: cost and latency grow with every edit, and most intermediate states are rewritten
    before they matter.
- **No cache.** Rejected: Stop fires more than once in a session, and each firing would
    re-judge units that did not change since the previous one.
- **A harness-side cache keyed by rule, backend, model, and unit hash.** Rejected: `jev-lint` already caches verdicts
    and batches subjects per file, so a second cache would duplicate it and could disagree with it.
- **One `jev-lint run` call per rule and file.** Rejected: it forgoes `jev-lint`'s batching of up to 256 subjects per
    file and its subject selection, and multiplies process starts and model calls.
- **Keeping the cache inside the repository.** Rejected: `jev-lint` treats the cache as trusted input that can silence
    rules, so it must not live where the agent or a commit can alter it.

Revisit when false-positive reports after promotion show that the example tests are not a sufficient criterion, when
the lack of a cross-tool inventory hides rules that are still prose or duplicated, when Stop-time findings are mostly
ignored or arrive too late to act on, when `jev-lint`'s cache hit rate is too low to repay the model cost, or when the replacement
conditions of ADR-0020 are met.
