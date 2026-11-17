---
status: accepted
date: 2026-11-01
---

# Store session receipts as one JSON file per session

## Context and Problem Statement

The Stop hook must find the verification receipt of a session after the agent process has exited. Receipts are written
by one hook and read by another, never by two writers at once.

## Considered Options

* One JSON file per session under the state directory
* One shared JSON file keyed by session ID
* SQLite

## Decision Outcome

Chosen option: "One JSON file per session", because a crashed hook can then corrupt only its own receipt, and removing
a finished session is a single `rm` instead of a locked rewrite of a shared file.

### Consequences

* Good, because no lock is needed between sessions.
* Bad, because the state directory grows by one file per session until it is pruned.
