---
status: accepted
date: 2026-11-11
---

# Name test files after the module under test

## Context and Problem Statement

A reader cannot find the tests of a module when test files are named freely.

## Considered Options

* `test_<module>.py`
* Name the file whatever seems best
* Do something else
* Another approach

## Decision Outcome

Chosen option: "`test_<module>.py`", because pytest collects it by default and the name tells the reader which module
it covers.

### Consequences

* Good, because tests are easy to find.
