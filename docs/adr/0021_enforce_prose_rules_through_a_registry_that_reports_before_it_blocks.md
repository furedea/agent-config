# ADR-0021: Enforce prose rules through a registry that reports before it blocks

- Status: Proposed
- Date: 2026-11-10

In the context of turning the prose rules of `AGENTS.md` and the style skills into machine checks (#74), facing
rules that differ in how they can be judged (existing linter, ast-grep, model, prose only) and a model judge whose
cutoffs are not yet fitted (ADR-0020), we decided for one registry of rule files under
`agents/lint/rules/<language>/<id>.yml`, whose hook returns findings to the agent without blocking, promotes a rule
to blocking only after its example tests show no false positive, runs model-judged rules once at Stop over the changed
units, caches a raw score by rule id, rule version, model, and content hash of the judged unit, and pins `jev-lint` with its
dependencies through Nix behind the backend abstraction, and against blocking on edit, judging per edit, and running
without a cache, to achieve rules that are declared once, traceable to their source text, and enforced without
stopping the agent on an unproven rule or paying for repeated model calls, accepting that an unpromoted rule can be
ignored by the agent, that a Stop-time verdict arrives after the edits it judges, and that a rule version must be
bumped by hand whenever its meaning changes.

## Decisions

- **Registry shape.** One YAML file per rule. Required fields: `id`, `source` (a link to the line of `AGENTS.md` or
  the style skill that states the rule), `language`, `method` (`linter`, `ast-grep`, `model`, or `prose`),
  `threshold` (required for `model`, otherwise absent), `version`, and `examples` with at least one conforming and
  one violating case. A `linter` rule names the linter's own rule code and holds no logic. A test fails when a
  `source` link does not resolve to an existing file and line, or when the quoted rule text no longer appears there,
  so a prose edit cannot silently orphan a rule. `prose` records a rule that stays text only, so that the inventory
  is complete.
- **Hook behaviour.** Findings are returned to the agent as feedback and never block. A rule becomes blocking only
  when its example tests pass with no false positive on the conforming examples and on the repository's own files;
  the promotion is a reviewed change to the rule file. Model-judged rules are not promoted until their cutoff has
  been fitted on a larger corpus, as ADR-0020 requires.
- **Judging time.** Static rules run on the files changed by each edit. Model-judged rules run once at Stop over the
  units (functions or classes selected by ast-grep) changed in the session, not per edit.
- **Cache key.** Rule id, rule version, and content hash of the judged unit. The cache stores the raw score, not
  the pass/fail verdict, and applies the rule's `threshold` after the lookup, so retuning a cutoff needs no
  invalidation. The backend and model identifier are part of the key, so a model change invalidates every entry.
  Changing a rule's meaning without bumping its version is a defect; the rule's example tests are the check.
- **Backend.** `jev-lint` is pinned with all its dependencies through Nix and never fetched with `npx` at run time,
  and the hook calls it only through the backend interface, so that ADR-0020's replacement stays possible. This
  replaces only the run mode of ADR-0020 (`npx` over a Nix-provided Node, whose transitive dependencies were not
  pinned); ADR-0020's choice of `jev-lint` stands, and both ADRs are still Proposed. When no key is available,
  model-judged rules are reported as "N unjudged" and never skipped silently.

## Alternatives considered

- **Block on edit.** Rejected: an unproven rule would stop the agent on false positives, and the model judge is
  not yet precise enough (ADR-0020).
- **Judge per edit.** Rejected: cost and latency grow with every edit, and most intermediate states are rewritten
  before they matter.
- **No cache.** Rejected: Stop would re-judge unchanged units on every session.
- **Rules inside each tool's own config only.** Rejected: ast-grep and model rules have no place there, and the
  source link and examples would have no common home.

Revisit when false-positive reports after promotion show that the example tests are not a sufficient criterion, when
Stop-time findings are mostly ignored or arrive too late to act on, when the cache hit rate is too low to repay the
key, or when the replacement conditions of ADR-0020 are met.
