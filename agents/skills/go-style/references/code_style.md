# Go Code Conventions

## Formatting

- gofumpt and goimports decide formatting and import grouping. Do not hand-format around them.

## Naming

- Use short, lowercase, single-word package names without underscores.
- Avoid stutter: `config.Loader`, not `config.ConfigLoader`.
- Cast initialisms consistently: `ID`, `URL`, `HTTP`, not `Id`, `Url`, `Http`.
- Use short receiver names (one or two letters), the same across a type's methods.
- Let name length match scope: `i` in a short loop, a descriptive name for a package-level identifier.
- Avoid `manager`, `helper`, `util`, and `common` unless the name is already established locally.

## Comments and Documentation

- Doc comments on exported identifiers start with the identifier name: `// Load reads ...`.
- Comments explain why, not what.
- Architectural choices, dependency decisions, and external-tool boundary rules belong in ADRs.

## Logging and Diagnostics

- Use `log/slog` for logging.
- Keep human diagnostics on stderr and machine-readable command output on stdout.
- Libraries must not configure the global logger.
