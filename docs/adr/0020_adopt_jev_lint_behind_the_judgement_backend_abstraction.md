# ADR-0020: Adopt jev-lint behind the judgement backend abstraction

- Status: Proposed
- Date: 2026-11-07

In the context of enforcing rules that only a model can judge (the prose rules of `AGENTS.md` and the
style skills), where Jev-family tools are all under two months old and none is the standard, facing a
choice between `mizchi/jev-lint`, `codegirl-007/jevlint`, and a minimal implementation of our own, we
decided for adopting `jev-lint`, pinned to the npm release and run through Nix (`nodejs_24` and
`ast-grep` with `npx`), behind the backend abstraction of #74 so that the backend can be replaced, and
against `jevlint` and against building our own now, to achieve ast-grep extraction as in the
issue's design, reported tokens and cost per run, and a pinned run that needs neither CGO nor a global
install, accepting that `jev-lint` supports only the TypeSafe provider (Clef is experimental), that its
latest npm release (0.7.0) lags the repository (0.7.1), and that a model call sends the judged source to
TypeSafe.

Evidence: the measurement and the maintenance comparison are in
[issue #75](https://github.com/furedea/agent-config/issues/75) and `docs/spikes/jev/`. On seven rules
and 42 labelled Python functions with the same model (`jev-latest`), both tools reached precision 1.00
and recall 0.90 within 0.1 s per judgement, so accuracy does not separate them; the sample is small,
author-labelled, and run once, and the two tools missed different functions. The criterion "installable
with Nix" was read as "runs pinned and reproducibly through Nix", because neither tool is in nixpkgs;
`jevlint` builds only with the system clang, since the Nix clang cannot link `-lresolv`.

Revisit when the abstraction of #74 needs a second provider (`jevlint` supports OpenRouter and OpenAI
Decisions), when `jev-lint` publishes no release for three months, or when a minimal own
implementation (ast-grep for extraction, one request per file to the TypeSafe API; about 200 lines of
Python plus tests, an estimate that was not built) becomes cheaper than following the tool.
