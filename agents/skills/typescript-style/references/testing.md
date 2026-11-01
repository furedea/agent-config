# TypeScript Testing

Use `tsdd` to decide when to add or reuse tests, which behavior to cover, and the appropriate
verification level. The conventions below govern TypeScript test tooling and structure.

- Use only `vitest` as test framework, with globals enabled; do not add Jest.
- Run tests with `pnpm run test`.
- Use `it.each` for the same behavior across multiple inputs.
- Prefer fake implementations over mocks. Use `vi.mock` only for external dependencies at module boundaries.
- Inject time and randomness as arguments (for example an `Rng` function) instead of reading
  `Date.now()` or `Math.random()` inside logic.
- Use temporary directories for filesystem tests. Do not touch the real home directory.
- Record a reproduced defect with Vitest `test.fails` and a comment naming the condition for
  removing it; `test.fails` fails the run when the test unexpectedly passes. Remove the marker in
  the change that fixes the defect.

## Mutation Testing

Use StrykerJS (10.x) with the Vitest runner when `tsdd` calls for mutation testing; add
`@stryker-mutator/core` and `@stryker-mutator/vitest-runner` as dev dependencies only when needed.

- Set `"testRunner": "vitest"` in `stryker.config.json`.
- Scope a run to the changed module:
  `pnpm exec stryker run --mutate "src/engine/cohort.ts"`
- Read survivors in the clear-text output or the HTML report under `reports/`
  (`reports/mutation.html` by default).
- Keep `.stryker-tmp/` and `reports/` out of version control.

## Test Structure

- **Unit test**: `*.test.ts` next to the module under test.
- **End-to-end test**: under `tests/`.
- **Helper function**: prefer local helpers when setup is lightweight or argument-driven.
- **Fake implementation**: prefer explicit fake objects over global mocks.
