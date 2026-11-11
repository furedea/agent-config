package fixture

import (
	"errors"
	"fmt"
	"os"
)

func LoadConfig(path string) ([]byte, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config %s: %w", path, err)
	}
	return data, nil
}

func ParsePort(raw string) (int, error) {
	if raw == "" {
		return 0, errors.New("parse port: value is empty")
	}
	return len(raw), nil
}

func wrap(operation, subject string, err error) error {
	return fmt.Errorf("%s %s: %w", operation, subject, err)
}

func Remove(path string) error {
	if err := os.Remove(path); err != nil {
		return wrap("remove", path, err)
	}
	return nil
}

func Forward(path string) error {
	if _, err := os.Stat(path); err != nil {
		return err
	}
	return errors.New("stat " + path + ": already exists")
}
