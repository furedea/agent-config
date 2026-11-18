package fixture

import (
	"context"
	"os"
	"os/signal"
	"sync"
	"time"
)

func Process(items []string, handle func(string)) {
	var wg sync.WaitGroup
	for _, item := range items {
		wg.Add(1)
		go func(item string) {
			defer wg.Done()
			handle(item)
		}(item)
	}
	wg.Wait()
}

func Tick(ctx context.Context, work func()) <-chan struct{} {
	done := make(chan struct{})
	go func() {
		defer close(done)
		ticker := time.NewTicker(time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				work()
			}
		}
	}()
	return done
}

func Compute(values []int) int {
	result := make(chan int)
	go func() {
		total := 0
		for _, value := range values {
			total += value
		}
		result <- total
	}()
	return <-result
}

func ListenForInterrupt(onInterrupt func()) {
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt)
	// Lives as long as the process: the handler must run on every interrupt until exit.
	go func() {
		for range signals {
			onInterrupt()
		}
	}()
}
