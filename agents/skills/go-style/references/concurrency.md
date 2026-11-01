# Concurrency

- Pass `context.Context` as the first parameter, named `ctx`; never store it in a struct.
- Give every goroutine a defined owner and a termination path (context cancellation, closed
  channel, or `WaitGroup`). Do not start a goroutine whose end nobody waits for.
- Use `errgroup` for parallel work that returns errors; it propagates the first error and cancels the context.
- The sender closes a channel, never the receiver; do not close a channel from several senders.
- Place a `sync.Mutex` directly above the fields it guards and document the guarded set.
- Prefer passing data over sharing memory; use a mutex when the state is truly shared.
- Run tests with `-race`.

```go
g, ctx := errgroup.WithContext(ctx)
for _, url := range urls {
	g.Go(func() error { return fetch(ctx, url) })
}
if err := g.Wait(); err != nil {
	return fmt.Errorf("fetch all: %w", err)
}
```
