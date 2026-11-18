package fixture

import (
	"fmt"
	"log/slog"
	"os"
)

func LoadConfig(path string) ([]byte, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		slog.Error("read config", "path", path, "err", err)
		return nil, err
	}
	return data, nil
}

func Save(path string, data []byte) error {
	if err := os.WriteFile(path, data, 0o600); err != nil {
		slog.Error("save failed", "path", path, "err", err)
		return fmt.Errorf("save %s: %w", path, err)
	}
	return nil
}

type Store struct {
	logger *slog.Logger
}

func (s *Store) Remove(path string) error {
	err := os.Remove(path)
	if err != nil {
		s.logger.Error("remove", "path", path, "err", err)
	}
	return err
}
