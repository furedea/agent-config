# TypeScript Code Conventions

## Naming

- Name files by the domain or action, not a role suffix: `format.ts`, not `formatter.ts`.

## Separation of Concerns

- Keep user-facing wording separate from logic, in a dedicated module such as `src/copy/`, so logic
    is testable without prose.

## Comments and Documentation

- Comments explain why, not what.
- Prefer clear types, function names, and module boundaries over explanatory comments.
- Architectural choices, dependency decisions, and external-tool boundary rules belong in ADRs.
