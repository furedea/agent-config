package fixture

import (
	"embed"
	"fmt"
	"regexp"
)

//go:embed defaults.json
var files embed.FS

var defaults = mustRead("defaults.json")

func mustRead(name string) []byte {
	data, err := files.ReadFile(name)
	if err != nil {
		panic(fmt.Sprintf("embedded %s is missing: %v", name, err))
	}
	return data
}

func MustPattern(expression string) *regexp.Regexp {
	pattern, err := regexp.Compile(expression)
	if err != nil {
		panic(err)
	}
	return pattern
}

type State int

const (
	Idle State = iota
	Running
)

func (s State) String() string {
	switch s {
	case Idle:
		return "idle"
	case Running:
		return "running"
	default:
		panic(fmt.Sprintf("unknown state %d", int(s)))
	}
}

func Divide(total, parts int) int {
	if parts <= 0 {
		panic("Divide: parts must be positive; callers check it")
	}
	return total / parts
}
