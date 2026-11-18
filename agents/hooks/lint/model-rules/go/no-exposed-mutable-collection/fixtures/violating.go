package fixture

type Cart struct {
	items []Item
}

func (c *Cart) Items() []Item {
	return c.items
}

type Registry struct {
	handlers map[string]Handler
}

func (r *Registry) Handlers() map[string]Handler {
	return r.handlers
}

type Queue struct {
	pending []string
	limit   int
}

func (q *Queue) Pending() []string {
	if len(q.pending) > q.limit {
		return q.pending[:q.limit]
	}
	return q.pending
}

type Item struct{ Name string }
type Handler func()
