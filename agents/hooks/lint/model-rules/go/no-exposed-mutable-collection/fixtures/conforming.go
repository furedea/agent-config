package fixture

import (
	"slices"
	"strings"
)

type Response struct {
	Items []string `json:"items"`
}

func (r Response) Names() []string {
	return r.Items
}

type Library struct {
	books []string
}

type catalog struct {
	titles []string
}

func (l *Library) Titles() []string {
	view := catalog{titles: slices.Clone(l.books)}
	return view.titles
}

type parsed struct {
	fields []string
}

func Fields(line string) []string {
	result := parsed{fields: strings.Split(line, ",")}
	return result.fields
}
