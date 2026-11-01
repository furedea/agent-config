# TypeScript Code Conventions

## Naming

- Use snake_case file names (enforced by ls-lint), for example `long_run.ts`.
- Name files by the domain or action, not a role suffix: `format.ts`, not `formatter.ts`.
- Avoid `manager`, `helper`, `util`, and `common` unless the name is already established locally.

## Imports

- Use `import type` for type-only imports, as `verbatimModuleSyntax` requires.
- Prefer explicit named imports over namespace imports.
- Do not create import cycles; `import/no-cycle` enforces this.

## Formatting

- Let oxfmt define formatting. Do not hand-format around it.

## Separation of Concerns

- Keep user-facing wording separate from logic, in a dedicated module such as `src/copy/`, so logic
  is testable without prose.

## Comments and Documentation

- Comments explain why, not what.
- Prefer clear types, function names, and module boundaries over explanatory comments.
- Architectural choices, dependency decisions, and external-tool boundary rules belong in ADRs.
