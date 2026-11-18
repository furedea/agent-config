package main

import (
	"flag"
	"fmt"
	"net/http"
	"os"
	"time"

	"example.com/sync/internal/mirror"
)

func main() {
	source := flag.String("source", "", "URL to mirror")
	flag.Parse()
	var err error
	for attempt := 1; attempt <= 5; attempt++ {
		var response *http.Response
		response, err = http.Get(*source)
		if err == nil && response.StatusCode < 500 {
			err = mirror.Save(response)
			break
		}
		time.Sleep(time.Duration(attempt*attempt) * time.Second)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
