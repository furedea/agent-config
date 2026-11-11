package fixture

import (
	"errors"
	"fmt"
	"os"
)

func Validate(name string) error {
	if name == "" {
		return errors.New("invalid")
	}
	return nil
}

func Open(path string) (*os.File, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("failed")
	}
	return file, nil
}

func Parse(raw string) (int, error) {
	if raw == "" {
		return 0, errors.New("config")
	}
	return len(raw), nil
}

func Load(path string) ([]byte, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("load failed")
	}
	return data, nil
}
