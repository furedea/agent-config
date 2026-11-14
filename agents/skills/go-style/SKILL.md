---
name: go-style
description: >
    User-specific conventions for designing, writing, testing, and reviewing code in existing
    Go projects. Initial project scaffolding belongs to project-setup.
---

# Go Coding Style Guidelines

## Scope

This skill governs **code written inside an already-bootstrapped Go project** — package layout, types, error handling, concurrency, test authoring, refactoring, code review, and naming.

Requested project initialization or Nix environment setup belongs to `project-setup`. Apply these
development conventions once the project's selected Go toolchain and required dependencies are
usable. Routine Go edits do not authorize introducing Nix or changing GitHub settings; preserve
the existing environment workflow.

## Task-Specific References

| Task                                                          | Read                                         |
| ------------------------------------------------------------- | -------------------------------------------- |
| Dependencies, package layout, tool commands, or lint gates    | [Project tooling](references/tooling.md)     |
| Types, constructors, enums, sum types, or interfaces          | [Types](references/types.md)                 |
| Fallible operations, wrapping, sentinel errors, or panics     | [Error handling](references/errors.md)       |
| Writing, running, or reviewing tests                          | [Testing](references/testing.md)             |
| Contexts, goroutines, channels, or locks                      | [Concurrency](references/concurrency.md)     |
| Naming, formatting, doc comments, or logging                  | [Code conventions](references/code_style.md) |

Read only the references relevant to the current task. For a focused review, use the references
for the affected concepts.
