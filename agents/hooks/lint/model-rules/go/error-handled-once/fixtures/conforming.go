package fixture

import (
	"fmt"
	"log/slog"
	"os"
)

func CleanUp(paths []string) {
	for _, path := range paths {
		if err := os.Remove(path); err != nil {
			slog.Warn("remove failed", "path", path, "err", err)
		}
	}
}

func Open(path string) (*os.File, error) {
	slog.Info("opening", "path", path)
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", path, err)
	}
	return file, nil
}

func ReadOrDefault(path string, fallback []byte) []byte {
	data, err := os.ReadFile(path)
	if err != nil {
		slog.Warn("using the default", "path", path, "err", err)
		return fallback
	}
	return data
}

func Retry(path string, attempts int) error {
	var last error
	for attempt := range attempts {
		if err := os.Remove(path); err != nil {
			slog.Debug("retrying", "attempt", attempt, "err", err)
			last = err
			continue
		}
		return nil
	}
	return fmt.Errorf("remove %s after %d attempts: %w", path, attempts, last)
}
