# Error Handling

- Return expected failures as values: `{ ok: true, value } | { ok: false, error }`, or the
  project's equivalent `Result` type. Define it once and reuse it.
- Make `error` a union of tagged variants when callers branch on the failure category.
- `throw` only for programmer errors and unrecoverable states, not for validation or lookups that
  can legitimately fail.
- Add context when rethrowing or converting: `new Error(message, { cause })`. The message names the
  operation and subject.
- Do not swallow errors with an empty `catch`; handle, convert, or rethrow.
- Await or explicitly handle every promise. The lint rules `no-floating-promises`,
  `no-misused-promises`, and `await-thenable` catch violations; do not disable them.

```ts
type Result<T, E> = { readonly ok: true; readonly value: T } | { readonly ok: false; readonly error: E };

async function readConfig(path: string): Promise<Result<Config, "unreadable" | "invalid">> {
  let text: string;
  try {
    text = await readFile(path, "utf8");
  } catch {
    return { ok: false, error: "unreadable" };
  }
  return parseConfig(text);
}
```
