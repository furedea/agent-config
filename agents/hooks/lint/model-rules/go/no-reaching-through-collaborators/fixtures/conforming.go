package fixture

import (
	"net/http"
	"sync"
	"time"
)

type Limiter struct {
	state struct {
		// mu guards count.
		mu    sync.Mutex
		count int
	}
	config struct {
		Window time.Duration
	}
}

func (l *Limiter) Allow() bool {
	l.state.mu.Lock()
	defer l.state.mu.Unlock()
	l.state.count++
	return l.state.count < 10
}

func (l *Limiter) WindowSeconds() float64 {
	return l.config.Window.Seconds()
}

func Origin(response *http.Response) string {
	return response.Request.URL.String()
}
