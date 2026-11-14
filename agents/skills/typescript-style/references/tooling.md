# TypeScript Project Tooling

## Package Management

- Use pnpm only; do not mix in npm or yarn, and do not introduce a competing lock file.
- Install from the lock with `pnpm install --frozen-lockfile`.
- Add dependencies with `pnpm add <package>` and development dependencies with `pnpm add -D <package>`.
- Do not use `@latest`-style version shortcuts in documentation or committed commands.
- Do not edit `pnpm-lock.yaml` manually.
- Do not add a dependency only because it is common. Add it when it removes real boundary complexity or prevents error-prone code.

## Tool Set

- Formatting is oxfmt, linting is oxlint, and type checking is `oxlint --type-aware --type-check`.
- Do not add ESLint, Prettier, or another type checker.
- Keep the strict `tsconfig.json` options (`strict`, `noUncheckedIndexedAccess`,
  `exactOptionalPropertyTypes`, `verbatimModuleSyntax`) and never loosen them to make code compile;
  fix the code instead.

## Directory Structure

- Store production code in `src/`.
- Colocate unit tests with the module as `*.test.ts`.
- Store end-to-end tests in `tests/`.
- Enforce layer boundaries with `no-restricted-imports` instead of review alone. Example: a pure
  calculation layer such as `src/engine/` imports no copy, data, or UI modules.
- Avoid `utils.ts` and `helpers.ts`; name modules by domain or action.

## Quality Gates

Confirm the relevant verification results before finishing TypeScript changes. Follow `tsdd`'s
Automatic Verification policy for execution needs and reuse of successful hook evidence. Run
verification through the `package.json` scripts, not the underlying binaries:

```bash
pnpm run format:check
pnpm run lint
pnpm run typecheck
pnpm run test
pnpm run knip
pnpm run check
```

`check` runs the others in sequence; use the project's stricter gate when defined.
