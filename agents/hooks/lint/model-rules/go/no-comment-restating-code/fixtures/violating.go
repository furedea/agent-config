package fixture

import "strings"

type Counter struct {
	hits int
}

func (c *Counter) Record() {
	// increment the counter
	c.hits++
}

func Names(users []User) []string {
	var names []string
	// loop over the users
	for _, user := range users {
		// append the name
		names = append(names, user.Name)
	}
	return names
}

func Normalize(raw string) string {
	// trim the spaces
	trimmed := strings.TrimSpace(raw)
	// make it lower case
	return strings.ToLower(trimmed)
}

type User struct {
	Name string
}
