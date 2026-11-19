import csv
import json
import smtplib
from pathlib import Path


def monthly_report(raw: bytes, out: Path) -> None:
    rows = []
    for line in raw.decode("utf-8").splitlines()[1:]:
        date, amount, category = line.split(",")
        rows.append((date[:7], int(amount), category.strip().lower()))
    totals = {}
    for month, amount, category in rows:
        totals[(month, category)] = totals.get((month, category), 0) + amount
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        for (month, category), amount in sorted(totals.items()):
            writer.writerow([month, category, f"{amount / 100:.2f}"])


def register_user(form, repository, mailer):
    if "@" not in form["email"] or len(form["password"]) < 12:
        raise ValueError(f"cannot register {form['email']}: invalid email or short password")
    user = repository.add(email=form["email"].strip().lower(), password=form["password"])
    message = f"Subject: Welcome\r\nTo: {user.email}\r\n\r\nHello {user.email.split('@')[0]},\r\nthanks."
    with smtplib.SMTP("localhost") as smtp:
        smtp.sendmail("noreply@example.com", [user.email], message)
    return user


def handle_request(raw, service):
    head, _, body = raw.partition(b"\r\n\r\n")
    headers = dict(line.split(b": ", 1) for line in head.split(b"\r\n")[1:])
    payload = json.loads(body[: int(headers[b"Content-Length"])])
    result = service.place_order(payload)
    encoded = json.dumps(result).encode()
    return b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(encoded)).encode() + b"\r\n\r\n" + encoded


def sync_inventory(source, target, log):
    items = source.fetch_items()
    changed = [item for item in items if target.differs(item)]
    target.apply(changed)
    log.write(f"{len(changed)} of {len(items)} items changed\n")
    source.mark_synced([item.id for item in items])


def publish_release(version, repository, registry, notifier):
    changelog = build_changelog(repository, version)
    artifact = build_artifact(repository, version)
    registry.upload(artifact)
    notifier.announce(version, changelog)


def parse_duration(text: str) -> int:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    total = 0
    number = ""
    for char in text.strip():
        if char.isdigit():
            number += char
        elif char in units and number:
            total += int(number) * units[char]
            number = ""
        else:
            raise ValueError(f"cannot parse duration {text!r}: unexpected {char!r}")
    if number:
        raise ValueError(f"cannot parse duration {text!r}: missing unit after {number}")
    return total


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
