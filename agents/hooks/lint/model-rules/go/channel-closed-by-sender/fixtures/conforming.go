package fixture

import "sync"

func Generate(limit int) <-chan int {
	out := make(chan int)
	go func() {
		defer close(out)
		for value := range limit {
			out <- value
		}
	}()
	return out
}

func Fan(sources [][]int) <-chan int {
	out := make(chan int)
	var wg sync.WaitGroup
	for _, source := range sources {
		wg.Add(1)
		go func(source []int) {
			defer wg.Done()
			for _, value := range source {
				out <- value
			}
		}(source)
	}
	go func() {
		wg.Wait()
		close(out)
	}()
	return out
}

type Server struct {
	quit chan struct{}
	once sync.Once
}

func (s *Server) Shutdown() {
	s.once.Do(func() { close(s.quit) })
}

func Watch(stop chan struct{}, signals <-chan bool) {
	for signal := range signals {
		if signal {
			close(stop)
			return
		}
	}
}
