---
status: accepted
date: 2026-11-08
---

# Use PostgreSQL for the job queue

## Context and Problem Statement

The service needs a durable job queue for about 50 jobs per minute. PostgreSQL is already deployed.

## Considered Options

* PostgreSQL with `SELECT ... FOR UPDATE SKIP LOCKED`
* Write jobs to a text file and read them back by hand
* Do nothing and lose jobs when the process restarts
* Build our own distributed message broker from scratch

## Decision Outcome

Chosen option: "PostgreSQL", because it is already deployed and 50 jobs per minute is far below what it handles.

### Consequences

* Bad, because queue load shares the database with application traffic.
