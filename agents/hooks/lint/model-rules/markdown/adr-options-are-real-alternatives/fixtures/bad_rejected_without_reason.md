---
status: accepted
date: 2026-11-10
---

# Run the linter in a pre-push hook

## Context and Problem Statement

Lint failures reach CI because nothing runs the linter before the push, and each failure costs a CI round trip.

## Considered Options

* A pre-push hook
* A pre-commit hook
* A watch mode in the editor
* A Makefile target
* A GitHub Action

## Decision Outcome

Chosen option: "A pre-push hook", because it runs once per push, after the commits are final, and a failure stops the
push before CI sees it.

### Consequences

* Bad, because a developer can still skip it with `--no-verify`.
