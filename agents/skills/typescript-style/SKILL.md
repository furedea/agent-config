---
name: typescript-style
description: >
    User-specific conventions for designing, writing, testing, and reviewing code in existing
    TypeScript projects. Initial project scaffolding belongs to project-setup.
---

# TypeScript Coding Style Guidelines

## Scope

This skill governs **code written inside an already-bootstrapped TypeScript project** — types, error handling, test authoring, refactoring, code review, naming, and imports.

Requested project initialization or Nix environment setup belongs to `project-setup`. Apply these
development conventions once the project's selected Node/pnpm environment and required
dependencies are usable. Routine TypeScript edits do not authorize introducing Nix or changing
GitHub settings; preserve the existing environment workflow.

## Task-Specific References

| Task                                                              | Read                                         |
| ----------------------------------------------------------------- | -------------------------------------------- |
| Dependencies, source layout, tool commands, or type checking      | [Project tooling](references/tooling.md)     |
| Unions, Value Objects, immutability, or input parsing             | [Types](references/types.md)                 |
| Fallible operations, error values, throwing, or promises          | [Error handling](references/errors.md)       |
| Writing, running, or reviewing tests                              | [Testing](references/testing.md)             |
| File naming, imports, formatting, comments, or user-facing wording | [Code conventions](references/code_style.md) |

Read only the references relevant to the current task. For a focused review, use the references
for the affected concepts.
