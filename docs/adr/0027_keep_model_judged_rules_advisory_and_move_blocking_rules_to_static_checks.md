---
status: accepted
date: 2026-11-19
supersedes: [ADR-0021]
related: [ADR-0020, ADR-0021]
---

# Keep model-judged rules advisory and move blocking rules to static checks

## Context and Problem Statement

ADR-0021 lets a model-judged (jev-lint) rule be promoted to a gate that blocks every time once its example tests show no
false positive, and deletes the rule's prose when it is promoted. Since then 74 rules exist and the cutoffs of those
with fixtures have been fitted (#240–#244; the rest stay at the 0.5 starting value). The evidence is in: a fitted rule
has a small fixture set (a handful to under twenty cases) and some are blind, the verdict is probabilistic, and PRs already end at the Codex and Claude reviews and the ban on merging with an unresolved thread.
Should any model-judged rule ever block?

This decision replaces only ADR-0021's promotion decision (#249, #169). Everything else in ADR-0021 stands: static
rules block on edit, the Stop-time run, the cache, the trusted-owner gate, key handling and failure behaviour.

## Considered Options

* Promote a model-judged rule to a gate when its example tests pass (ADR-0021)
* Keep every model-judged rule advisory, and move a rule that must stop work to a static check

## Decision Outcome

Chosen option: "Keep every model-judged rule advisory, and move a rule that must stop work to a static check", because
a probabilistic verdict backed by 7 to 10 fixtures cannot justify stopping the agent: a false positive pushes the agent
to rewrite code to please the model's scoring, a missed finding costs little because the rules judge matters of
judgement that PR review still catches, and a gate would let an API outage or delay stop all work.

* A model-judged finding is shown to the agent at Stop and is never a gate that blocks every time. The one-time Stop
  block of ADR-0021's hook behaviour (findings on inputs not judged before block once, unchanged inputs never again)
  stays in force until #245 decides how findings are shown; what this ADR removes is the repeating gate.
  `severity: error` is not used for model rules.
* A rule that must block is stated deterministically as an ast-grep error rule or as the language's own linter check
  (see ADR-0021, "Which rules ast-grep may block"). A rule that cannot be restated deterministically is not suited to
  blocking and stays advisory or prose.
* The prose of a rule that has a model-judged check stays in `AGENTS.md` and the style skills. There is no promotion
  after which it could be deleted, and the check is a reminder, not the authority. ADR-0021's "prose is deleted, not
  kept" still applies to rules replaced by a static check or an existing linter.
* The 74 rules and their cutoffs, fitted or not, are unchanged.

### Consequences

* Good, because a model error or outage can no longer repeatedly gate or trap the agent or lead it to game the judge;
  until #245 changes how findings are shown, a false positive on new inputs can still stop it once.
* Good, because each rule has one clear route: deterministic and blocking, or advisory.
* Bad, because an agent may ignore an advisory finding and only review catches it.
* Bad, because the prose and the check of a model-judged rule both exist for good, so they can drift.
