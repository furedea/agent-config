---
status: accepted
date: 2026-11-02
---

# Keep the commit-message check out of CI

## Context and Problem Statement

The commit-message check calls a hosted model. CI has no API key, and adding one would expose it to pull requests from
forks.

## Decision Outcome

The check runs only on the developer's machine at commit time, because a key that CI jobs can read is a key every fork
PR can read, and an advisory check is not worth that exposure.

### Consequences

* Bad, because a commit made without the local hook is never checked.
