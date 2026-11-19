import xml.etree.ElementTree


def checkout(order, amount):
    order.customer.wallet.charge(amount)
    return order.customer.wallet.balance()


class ReportJob:
    __slots__ = ("app",)

    def __init__(self, app):
        self.app = app

    def run(self, sql):
        rows = self.app.container.database.execute(sql)
        return [row[0] for row in rows]


def remind(invoice):
    if invoice.overdue:
        invoice.account.owner.notify(f"Invoice {invoice.number} is overdue")


def ship(shipment):
    label = shipment.carrier.api.labels.create(shipment.address)
    return label.tracking_number


def parse_feed(text):
    root = xml.etree.ElementTree.fromstring(text)
    return [item.findtext("title") for item in root.iter("item")]


def repository_owner(event):
    return event.payload.repository.full_name.split("/")[0]


def prepare_cache(settings):
    settings.paths.cache.mkdir(parents=True, exist_ok=True)
    return settings.paths.cache


def utc_stamp(moment):
    return moment.astimezone().isoformat().replace("+00:00", "Z").strip()
