# Go Testing

Use `tsdd` to decide when to add or reuse tests, which behavior to cover, and the appropriate
verification level. The conventions below govern Go test tooling and structure.

- Use the standard `testing` package with testify.
- Run tests with `go test -race -cover ./...`.
- Use `require` for preconditions that make the rest of the test meaningless, and `assert` for outcomes.
- Use table-driven tests with `t.Run`; call `t.Parallel()` when cases share no state.
- Use `t.TempDir()` for files and `t.Setenv()` for environment; never touch the real home directory.
- Keep golden files under `testdata/`, and use them only when exact output is part of the behavior.
- Go's `testing` package has no strict expected-failure marker; do not use a stacked PR to record
  a reproduced defect.

## Mutation Testing

Go has no de facto mutation testing tool. Use `gremlins` (0.6.x) when `tsdd` calls for mutation
testing; it is pre-1.0, so flags and configuration can change between minor releases. Add it with
`go get -tool github.com/go-gremlins/gremlins/cmd/gremlins` only when needed.

- Scope a run to a package: `go tool gremlins unleash ./internal/foo`
- Run `go tool gremlins unleash --help` to confirm the flags of the pinned version; `--dry-run`
  lists mutants without running tests and `--output <file>` writes a JSON report.
- Treat `LIVED` mutants as survivors; `NOT COVERED` means no test reaches the code.
- Keep any report file out of version control.

## Test Structure

- **Black-box test**: `package foo_test` for public API.
- **White-box test**: `package foo` only when internals are needed.
- **Helper function**: call `t.Helper()` first; keep helpers local unless several test files share them.
- **Fake implementation**: an explicit type implementing the consumer's small interface.

```go
func TestNewPort(t *testing.T) {
	tests := []struct {
		name    string
		value   int
		wantErr bool
	}{
		{"valid", 8080, false},
		{"zero", 0, true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := foo.NewPort(tt.value)
			assert.Equal(t, tt.wantErr, err != nil)
		})
	}
}
```
