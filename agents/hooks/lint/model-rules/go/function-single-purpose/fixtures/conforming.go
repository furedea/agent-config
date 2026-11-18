package fixture

import (
	"context"
	"strings"
)

type Pipeline struct {
	source Source
	sink   Sink
}

func (p *Pipeline) Run(ctx context.Context) error {
	records, err := p.source.Fetch(ctx)
	if err != nil {
		return err
	}
	cleaned := clean(records)
	return p.sink.Write(ctx, cleaned)
}

func clean(records []string) []string {
	var cleaned []string
	for _, record := range records {
		record = strings.TrimSpace(record)
		if record == "" || strings.HasPrefix(record, "#") {
			continue
		}
		cleaned = append(cleaned, strings.ToLower(record))
	}
	return cleaned
}

func (p *Pipeline) Close() error {
	return p.sink.Close()
}

type Source interface {
	Fetch(ctx context.Context) ([]string, error)
}

type Sink interface {
	Write(ctx context.Context, records []string) error
	Close() error
}
