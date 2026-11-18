package fixture

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
)

func ReadSettings(path string) []byte {
	data, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	return data
}

func ParsePort(raw string) int {
	port, err := strconv.Atoi(raw)
	if err != nil {
		panic("bad port: " + raw)
	}
	return port
}

func Decode(response *http.Response, target any) {
	if response.StatusCode != http.StatusOK {
		panic("unexpected status " + response.Status)
	}
	if err := json.NewDecoder(response.Body).Decode(target); err != nil {
		panic(err)
	}
}
