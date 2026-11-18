package fixture

import (
	"context"
	"os"

	"example.com/billing/internal/payments"
	"example.com/billing/internal/storage"
)

func NewSettler() *Settler {
	client := payments.NewPaymentsClient(payments.Options{APIKey: os.Getenv("PAYMENTS_KEY"), Retries: 3})
	return &Settler{client: client}
}

func Run(ctx context.Context, ids []string) error {
	store := storage.NewBlobStore(os.Getenv("BUCKET"))
	settler := &Settler{client: payments.NewPaymentsClient(payments.Options{APIKey: os.Getenv("PAYMENTS_KEY")})}
	return NewApp(store, settler).Settle(ctx, ids)
}

type Settler struct {
	client *payments.Client
}

func (s *Settler) Settle(ctx context.Context, id string) error {
	reader := payments.NewInvoiceReader(s.client)
	invoice, err := reader.Read(ctx, id)
	if err != nil {
		return err
	}
	return s.client.Settle(ctx, id, invoice.Due)
}
