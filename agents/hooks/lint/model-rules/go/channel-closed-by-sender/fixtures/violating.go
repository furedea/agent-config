package fixture

import "sync"

func Sum(values chan int) int {
	total := 0
	for value := range values {
		total += value
	}
	close(values)
	return total
}

func Merge(sources [][]int) chan int {
	out := make(chan int)
	for _, source := range sources {
		go func(source []int) {
			for _, value := range source {
				out <- value
			}
			close(out)
		}(source)
	}
	return out
}

type Pool struct {
	jobs chan func()
	wg   sync.WaitGroup
}

func (p *Pool) Stop(worker int) {
	if worker == 0 {
		close(p.jobs)
	}
}

func (p *Pool) Fail() {
	close(p.jobs)
}
