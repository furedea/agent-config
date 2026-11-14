# Go Project Tooling

## Package Management

- Add dependencies with `go get <module>` and keep `go.mod` and `go.sum` consistent with `go mod tidy`.
- Pin development tools with `go get -tool <module>` and run them as `go tool <name>`.
- Do not use `go install <module>@latest` or other `@latest`-style shortcuts in documentation or committed commands.
- Assume `GOTOOLCHAIN=local`: the toolchain comes from the project environment, and Go must not download another one.
- Do not edit `go.sum` manually.
- Do not add a dependency only because it is common. Add it when it removes real boundary complexity or prevents error-prone code.

## Directory Structure

- Start with `main.go` at the module root.
- Move to `cmd/<name>/main.go` when the module has several commands.
- Put non-public packages under `internal/`.
- Do not create `pkg/`, `util/`, or `common/`; name packages by domain.
- Keep `main` thin: parse flags, wire dependencies, and call library code.

## Quality Gates

Confirm the relevant verification results before finishing Go changes. Follow `tsdd`'s Automatic
Verification policy for execution needs and reuse of successful hook evidence. The default
commands are below; use the project's stricter gate when defined:

```bash
golangci-lint fmt --diff
golangci-lint run
go test -race ./...
govulncheck ./...
```

- Do not loosen linter configuration to make code pass; fix the code.
