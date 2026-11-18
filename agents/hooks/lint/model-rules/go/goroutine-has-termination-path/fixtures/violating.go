package fixture

import (
	"net/http"
	"time"
)

type Cache struct {
	entries map[string]string
}

func (c *Cache) StartRefresh(fetch func() map[string]string) {
	go func() {
		for {
			c.entries = fetch()
			time.Sleep(time.Minute)
		}
	}()
}

func Notify(url string) {
	go http.Get(url)
}

func Watch(events <-chan string, handle func(string)) {
	go func() {
		for {
			handle(<-events)
		}
	}()
}
