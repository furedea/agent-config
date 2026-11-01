# Types

## Structs

- Keep fields unexported when the type has invariants, and construct it with
  `NewX(...) (X, error)` that validates once.
- Prefer a useful zero value when no invariant requires construction.
- Avoid boolean parameters; use typed constants.

```go
type Port struct{ value int }

func NewPort(value int) (Port, error) {
	if value < 1 || value > 65535 {
		return Port{}, fmt.Errorf("port %d out of range", value)
	}
	return Port{value: value}, nil
}
```

## Enums

- Declare enums as a typed constant block with `iota` and a `String()` method.
- Handle them with a `switch`; the `exhaustive` linter reports missing cases.

```go
type State int

const (
	StatePending State = iota
	StateDone
)

func (s State) String() string {
	switch s {
	case StatePending:
		return "pending"
	case StateDone:
		return "done"
	}
	return fmt.Sprintf("State(%d)", int(s))
}
```

## Sum Types

- Model data-carrying variants as an interface with an unexported marker method, annotated
  `//sumtype:decl`; `gochecksumtype` checks type switches for exhaustiveness.

```go
//sumtype:decl
type Payment interface{ isPayment() }

type Card struct{ Last4 string }
type Cash struct{}

func (Card) isPayment() {}
func (Cash) isPayment() {}
```

## Interfaces

- Keep interfaces small and define them in the consuming package, not next to the implementation.
- Accept interfaces, return concrete types.
- Do not introduce an interface until there is a second implementation or a test fake needs it.
