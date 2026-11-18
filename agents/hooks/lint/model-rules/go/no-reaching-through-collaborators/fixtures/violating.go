package fixture

type Notifier struct {
	account *Account
}

func (n *Notifier) Welcome(name string) error {
	return n.account.Owner.Mailer.Send(name, "welcome")
}

type Handler struct {
	server *Server
}

func (h *Handler) Purge(table string) error {
	_, err := h.server.store.db.Exec("DELETE FROM " + table)
	return err
}

func Charge(order *Order, cents int) error {
	return order.Customer.Wallet.Card.Charge(cents)
}

type Account struct{ Owner *Owner }
type Owner struct{ Mailer Mailer }
type Mailer interface{ Send(to, subject string) error }
type Server struct{ store *Store }
type Store struct{ db DB }
type DB interface{ Exec(query string) (int, error) }
type Order struct{ Customer *Customer }
type Customer struct{ Wallet *Wallet }
type Wallet struct{ Card Card }
type Card interface{ Charge(cents int) error }
