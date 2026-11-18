---
status: accepted
date: 2026-11-09
---

# Validate input with Pydantic

## Context and Problem Statement

Raw JSON from the hook protocol must be parsed into typed values once at the boundary.

## Considered Options

* Pydantic models
* Typed model classes from the Pydantic library
* Pydantic `BaseModel` subclasses

## Decision Outcome

Chosen option: "Pydantic models", because the hook already depends on Pydantic and its errors name the failing field.

### Consequences

* Bad, because a Pydantic upgrade can change error text.
