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

The shared file was rejected because every writer would need a lock and a crash during a rewrite loses every session.
SQLite was rejected because the hook runs in a sandbox that cannot write a journal file next to the database, and a
dependency would be added for a record that is read once.

### Consequences

* Bad, because the state directory grows by one file per session until it is pruned.
