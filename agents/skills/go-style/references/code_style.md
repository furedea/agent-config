# Go Code Conventions

## Naming

- Use short, single-word package names.
- Let name length match scope: `i` in a short loop, a descriptive name for a package-level identifier.

## Comments and Documentation

- Comments explain why, not what.
- Architectural choices, dependency decisions, and external-tool boundary rules belong in ADRs.

## Logging and Diagnostics

- Keep human diagnostics on stderr and machine-readable command output on stdout.
- Libraries must not configure the global logger.
