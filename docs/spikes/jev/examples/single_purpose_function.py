import json
import re


def parse_port(text):
    return int(text.strip())


def total_price(items):
    return sum(item.price * item.quantity for item in items)


def render_invoice_line(item):
    return f"{item.name}: {item.price * item.quantity}"


def process_order(order, db, mailer, logger):
    total = 0
    for item in order.items:
        total += item.price * item.quantity
    db.execute("INSERT INTO orders VALUES (?, ?)", (order.id, total))
    mailer.send(order.email, "Thanks for your order " + str(total))
    logger.write(json.dumps({"order": order.id, "total": total}))
    return total


def load_and_summarize(path):
    with open(path) as handle:
        raw = handle.read()
    rows = [line.split(",") for line in raw.splitlines()]
    totals = {}
    for name, amount in rows:
        totals[name] = totals.get(name, 0) + int(amount)
    for name, amount in sorted(totals.items()):
        print(f"{name:<20}{amount:>10}")
    return totals


def register_user(form, db):
    if not re.match(r"[^@]+@[^@]+", form["email"]):
        raise ValueError("bad email")
    hashed = form["password"][::-1] + "salt"
    db.execute("INSERT INTO users VALUES (?, ?)", (form["email"], hashed))
    print("registered", form["email"])
    return {"status": "ok", "email": form["email"]}
