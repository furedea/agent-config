package main

import (
	"errors"
	"fmt"
	"os"

	"example.com/check/internal/check"
)

func main() {
	err := check.Run(os.Args[1:])
	switch {
	case err == nil:
		os.Exit(0)
	case errors.Is(err, check.ErrFindings):
		os.Exit(1)
	default:
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}
