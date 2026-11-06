from dataclasses import dataclass


@dataclass(frozen=True)
class Money:
    amount: int
    currency: str


@dataclass(frozen=True)
class Address:
    street: str
    city: str


def charge(account, money: Money):
    return account.balance - money.amount


def ship_to(order, address: Address):
    return f"{order.id} -> {address.street}, {address.city}"


def render_label(name, width):
    return name.ljust(width)


def charge_card(args):
    return args["card"].charge(args["amount"], args["currency"])


def ship_order(params):
    street, city, zip_code = params
    return f"{street}, {city} {zip_code}"


def send_report(options):
    return options[0].send(options[1], options[2])
