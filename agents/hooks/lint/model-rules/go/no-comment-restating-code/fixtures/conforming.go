package fixture

import (
	"strings"
	"time"
)

func Backoff(attempt int) time.Duration {
	// The upstream rate limiter resets every 30 seconds, so waiting longer gains nothing.
	return min(time.Duration(attempt)*time.Second, 30*time.Second)
}

func Key(raw string) string {
	// Keys are compared case-insensitively by the storage service (see #142).
	return strings.ToLower(raw)
}

func Split(line string) []string {
	// Workaround for golang/go#12345: Fields drops a trailing empty column.
	return strings.Split(line, "\t")
}

func Total(prices []int) int {
	total := 0
	for _, price := range prices {
		// Prices are in cents; a float sum would round.
		total += price
	}
	return total
}
