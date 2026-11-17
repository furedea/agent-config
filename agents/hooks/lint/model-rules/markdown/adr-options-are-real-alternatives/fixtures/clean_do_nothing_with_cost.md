---
status: accepted
date: 2026-11-07
---

# Pin the formatter version in the flake

## Context and Problem Statement

A formatter upgrade rewrote 140 files in one unrelated PR, and reviewers could not tell the rewrite from the change.

## Considered Options

* Leave the formatter unpinned and accept the occasional mass rewrite
* Pin the version in `flake.lock` and update it in a dedicated PR

## Decision Outcome

Chosen option: "Pin the version", because leaving it unpinned already cost one unreadable review, and each further
upgrade would repeat it; a dedicated update PR keeps the rewrite apart from behaviour changes.

### Consequences

* Bad, because someone must open the update PR; Renovate does it weekly.
