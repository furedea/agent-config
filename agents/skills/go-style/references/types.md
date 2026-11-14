# Types

## Structs

- Keep fields unexported when the type has invariants, and construct it with
  `NewX(...) (X, error)` that validates once.
- Prefer a useful zero value when no invariant requires construction.
- Replace a boolean flag parameter with typed constants.

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

- Declare enums as a constant block with `iota` and give the type a `String()` method.

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

## Interfaces

- Keep interfaces small and define them in the consuming package, not next to the implementation.
- Accept an interface as a parameter.
- Do not introduce an interface until there is a second implementation or a test fake needs it.
