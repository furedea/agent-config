# Error Handling

- Return `error` as the last result.
- Wrap with the operation and subject: `fmt.Errorf("read config %s: %w", path, err)`.
- Define a sentinel error (`ErrNotFound`) or a custom error type only when callers branch on it.
- Do not log and return the same error; handle it at one level, usually the outermost.
- Do not ignore errors with `_`; handle them or explain why they are safe to drop.
- Use `panic` only for programmer errors and initialization failures, never for expected failures.

```go
var ErrNotFound = errors.New("not found")

func Load(path string) (Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Config{}, fmt.Errorf("read config %s: %w", path, err)
	}
	return parse(data)
}

// caller
if errors.Is(err, fs.ErrNotExist) {
	return defaults, nil
}
```
