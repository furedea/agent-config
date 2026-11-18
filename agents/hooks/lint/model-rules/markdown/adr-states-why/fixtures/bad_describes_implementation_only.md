---
status: accepted
date: 2026-11-05
---

# Cache verdicts in a JSON file

## Context and Problem Statement

The linter asks a model about each subject.

## Decision Outcome

The verdicts are cached in `verdicts.json`. The file is a JSON object whose keys are the SHA-256 of the subject text and
whose values are the score and the rule ID. The linter reads the file at startup, looks up each subject, sends the
misses to the model in batches of 256, and writes the file back after the run. The file lives under
`~/.local/state/agent-harness/model-rules/`. Entries are never removed. A lock file beside it serializes writers.

### Consequences

* The cache file is created on the first run.
