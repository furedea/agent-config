package fixture

import (
	"errors"
	"os"
	"slices"
	"strconv"
)

type Review struct {
	scores []float64
}

func Total(values []int) int {
	total := 0
	for _, value := range values {
		total += value
	}
	return total
}

func ReadConfig(path string) ([]byte, error) {
	return os.ReadFile(path)
}

func WriteReport(path string, body []byte) error {
	return os.WriteFile(path, body, 0o600)
}

func CheckPaths(paths []string) error {
	for _, path := range paths {
		if _, err := os.Stat(path); err != nil {
			return err
		}
	}
	return nil
}

func (r *Review) Judge(score float64) bool {
	return score >= 0.5
}

func LoadPort(name string) (int, error) {
	port, err := strconv.Atoi(os.Getenv(name))
	if err != nil {
		return 0, err
	}
	if port <= 0 {
		return 0, errors.New("port must be positive")
	}
	return port, nil
}

func FindLargest(values []int) int {
	sorted := slices.Clone(values)
	slices.Sort(sorted)
	if len(sorted) == 0 {
		return 0
	}
	return sorted[len(sorted)-1]
}

func (r *Review) Refresh(path string) error {
	body, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	score, err := strconv.ParseFloat(string(body), 64)
	if err != nil {
		return err
	}
	r.scores = []float64{score}
	return nil
}
