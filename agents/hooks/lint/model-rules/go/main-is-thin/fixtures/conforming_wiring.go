package main

import (
	"flag"
	"fmt"
	"net/http"
	"os"

	"example.com/shop/internal/orders"
	"example.com/shop/internal/store"
)

func main() {
	address := flag.String("listen", ":8080", "address to serve on")
	flag.Parse()
	db, err := store.Open(os.Getenv("DATABASE_URL"))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer db.Close()
	handler := orders.NewHandler(orders.NewService(db))
	if err := http.ListenAndServe(*address, handler); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
