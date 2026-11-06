# ADR-0020: Adopt jev-lint behind the judgement backend abstraction

- Status: Proposed
- Date: 2026-11-07

In the context of enforcing rules that only a model can judge (the prose rules of `AGENTS.md` and the
style skills), where Jev-family tools are all under two months old and none is the standard, facing a
choice between `mizchi/jev-lint`, `codegirl-007/jevlint`, and a minimal implementation of our own, we
decided for adopting `jev-lint` provisionally (仮採用：use it first and build our own if it proves unsatisfactory), pinned to the npm release and run through Nix (`nodejs_24` and
`ast-grep` with `npx`), behind the backend abstraction of #74 so that the backend can be replaced, and
against `jevlint` and against building our own now, to achieve ast-grep extraction as in the
issue's design, reported tokens and cost per run, and a pinned run that needs neither CGO nor a global
install, accepting that `jev-lint` supports only the TypeSafe provider (Clef is experimental), that its
latest npm release (0.7.0) lags the repository (0.7.1), and that a model call sends the judged source to
TypeSafe.

Evidence: the measurement and the maintenance comparison are in
[issue #75](https://github.com/furedea/agent-config/issues/75) and `docs/spikes/jev/`. On seven rules
and 47 Python functions (42 labelled, 5 value-object methods counted as conforming) with the same model
(`jev-latest`), both tools reached recall 0.90 within 0.13 s per judgement as whole-process wall time;
`jev-lint` had precision 1.00 and `jevlint` 0.90, exactly at the draft limit after two false positives
on value-object methods. At the unfitted default cutoff of 2, 15 of the 19 `jev-lint` hits were graded
only "arguable" (scores 2.06 to 2.49) and 4 "violation" (2.56 to 2.88); counting only the violation
level, recall would be 0.19. Every conforming function scored below the cutoff, so the classes
separate, but narrowly, and cutoffs must be fitted per rule on a larger corpus before any finding gates
a hook or CI. Accuracy therefore favours `jev-lint` only slightly: the sample is small,
author-labelled, and run once, and the tools missed different functions. The criterion "installable
with Nix" was read as "runs through Nix with a pinned tool version and no global install", because neither tool is in nixpkgs (the nixpkgs revision and the transitive npm dependencies of `npx` were not pinned in the spike);
`jevlint` builds only with the system clang, since the Nix clang cannot link `-lresolv`.

Revisit when using `jev-lint` produces dissatisfaction (then switch to our own implementation), when
the abstraction of #74 needs a second provider (`jevlint` supports OpenRouter and OpenAI
Decisions), when `jev-lint` publishes no release for three months, or when a minimal own
implementation (ast-grep for extraction, one request per file to the TypeSafe API; about 200 lines of
Python plus tests, an estimate that was not built) becomes cheaper than following the tool.
