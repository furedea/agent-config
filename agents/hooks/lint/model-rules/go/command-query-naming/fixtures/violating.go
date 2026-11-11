package fixture

import "os"

var seen = map[string]int{}

func GetCount(name string) int {
	seen[name]++
	return seen[name]
}

func SaveTotal(values []int) int {
	total := 0
	for _, value := range values {
		total += value
	}
	return total
}

func IsReady(path string) bool {
	if err := os.WriteFile(path, []byte("ready"), 0o600); err != nil {
		return false
	}
	return true
}

func DeleteName(name string) string {
	return name + "-deleted"
}
