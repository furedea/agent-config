package fixture

import (
	"context"
	"fmt"
	"os"

	"example.com/billing/internal/payments"
	"example.com/billing/internal/storage"
)

func SettleInvoices(ctx context.Context, ids []string) (int, error) {
	client := payments.NewPaymentsClient(payments.Options{
		APIKey:  os.Getenv("PAYMENTS_KEY"),
		Retries: 3,
	})
	settled := 0
	for _, id := range ids {
		invoice, err := client.Invoice(ctx, id)
		if err != nil {
			return settled, fmt.Errorf("fetch invoice %s: %w", id, err)
		}
		if invoice.Due > 0 && invoice.Approved {
			if err := client.Settle(ctx, id, invoice.Due); err != nil {
				return settled, fmt.Errorf("settle invoice %s: %w", id, err)
			}
			settled++
		}
	}
	return settled, nil
}

func ArchiveOld(ctx context.Context, days int) error {
	store := storage.NewBlobStore(os.Getenv("BUCKET"), storage.WithRegion("ap-northeast-1"))
	objects, err := store.List(ctx)
	if err != nil {
		return fmt.Errorf("list objects: %w", err)
	}
	for _, object := range objects {
		if object.AgeDays() > days {
			if err := store.Move(ctx, object.Key, "archive/"+object.Key); err != nil {
				return fmt.Errorf("archive %s: %w", object.Key, err)
			}
		}
	}
	return nil
}
