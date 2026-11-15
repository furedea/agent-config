# ADR-0023: Place skill responsibilities at the earliest sufficient tier

- Status: Proposed
- Date: 2026-11-15

In the context of workflow skills (`git-workflow`, `herdr-delegation`, `issue-workflow`, `adr`, `project-setup`,
`tsdd`, `measurement-evidence`, `source-of-truth`) that carry fixed command sequences, format rules, and state handling as
prose the agent re-interprets on every run, while the target architecture of #181 is still far from built, facing a
choice between keeping the prose, building the #181 control plane first, and moving responsibilities piecemeal, we
decided for placing each responsibility at the earliest tier that judges it sufficiently, in the order of #181 §3
(static checks, then dynamic checks, then fixed-question model judgement with `jev-lint`, then skill judgement), with
hooks, CI, and CLIs as the mechanisms that enforce or execute those results rather than as a tier of their own, and
for marking each mechanism as permanent (it survives #181: static checks, tests, typed skill outputs) or interim (it is
replaced by a #181 adapter: Herdr lane, delivery status, and Issue rendering helpers), where an interim mechanism keeps
no persistent state and creates no new source of truth, and against keeping the prose and against waiting for #181, to
achieve reproducible handling of what a machine can decide and skills that hold only judgement, accepting that interim
mechanisms will be rewritten when #181 lands, that a CLI the agent must choose to call still needs one line of prose
pointing to it, and that a thinned skill can change agent behaviour in ways only a before/after comparison of
representative tasks reveals.

A skill keeps two roles that no earlier tier can take. It states the constraints that static checks, dynamic checks,
and fixed-question judgement cannot decide, and it carries the development cycle the agent should follow when the
next step is a judgement rather than a fixed sequence: recognising the situation, choosing among options, composing
the mechanisms, and handing off to the next skill. For example, `project-setup` decides that a new project needs a
repository and which language, template, and visibility fit the requirements, runs `repo` once with those typed
arguments, and continues into the usual development cycle; the template mapping and the repository settings belong
to `repo`. Where part of a cycle turns out to be a fixed order with checkable conditions, that part moves to a
mechanism and the skill keeps the rest.

This extends ADR-0021 from the prose rules of `AGENTS.md` and the style skills to the workflow skills: as there, a rule
lives only in the mechanism that enforces it, and the prose is deleted in the change that adds the mechanism and its
tests. The rule inventory is planning information and lives in #169, not in the repository.

Revisit when #181 reaches a component that replaces an interim mechanism, or when a before/after comparison shows that
thinning a skill degraded the agent's behaviour.
