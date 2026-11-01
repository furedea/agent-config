# Types

## Unions

- Model states and kinds as discriminated unions with a tag field, not optional fields or flags.
- Handle a union with an exhaustive `switch` whose `default` branch assigns the value with
  `satisfies never`, so adding a variant fails compilation.

```ts
type Payment =
  | { readonly kind: "card"; readonly last4: string }
  | { readonly kind: "cash" };

function label(payment: Payment): string {
  switch (payment.kind) {
    case "card":
      return `card ${payment.last4}`;
    case "cash":
      return "cash";
    default:
      return payment satisfies never;
  }
}
```

## Value Objects

- Represent values with validation or invariants as branded types created by a validating `parse`
  function; the brand is not constructible elsewhere.

```ts
type Email = string & { readonly __brand: "Email" };

export function parseEmail(value: string): Result<Email, "invalid_email"> {
  return value.includes("@") ? { ok: true, value: value as Email } : { ok: false, error: "invalid_email" };
}
```

## Immutability

- Declare properties `readonly` and arrays `readonly T[]` by default.
- Do not expose a mutable raw collection from a domain type.

## Boundaries

- Accept external input (JSON, environment, network, storage) as `unknown` and parse it once at
  the boundary into constrained types. Do not re-validate the same value downstream.
- Do not use `as` casts except immediately after validation, as in the brand example above.
- Do not use `any`; use `unknown` and narrow.
- Group arguments into a type only when it names a real domain concept, never an anonymous object
  that mirrors one function's parameters.
