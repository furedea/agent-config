package main

import (
	"bufio"
	"fmt"
	"os"
	"strconv"
	"strings"
)

func main() {
	scanner := bufio.NewScanner(os.Stdin)
	totals := map[string]float64{}
	for scanner.Scan() {
		fields := strings.Split(scanner.Text(), ",")
		if len(fields) != 2 {
			continue
		}
		amount, err := strconv.ParseFloat(fields[1], 64)
		if err != nil {
			continue
		}
		totals[fields[0]] += amount * 1.1
	}
	for customer, total := range totals {
		fmt.Printf("%s\t%.2f\n", customer, total)
	}
}
