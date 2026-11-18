import enum


class OutputFormat(enum.StrEnum):
    CSV = "csv"
    JSON = "json"


def shipping_cost(method, weight_kg):
    if method == "standard":
        return 5 + weight_kg
    elif method == "express":
        return 15 + 2 * weight_kg
    elif method == "overnight":
        return 40 + 3 * weight_kg
    raise ValueError(f"unknown shipping method: {method}")


def describe_status(status):
    match status:
        case "pending":
            return "Waiting for payment"
        case "paid":
            return "Ready to ship"
        case "refunded":
            return "Money returned"
    return "Unknown"


def export(rows, fmt):
    writers = {"csv": write_csv, "json": write_json, "xml": write_xml}
    return writers[fmt](rows)


def is_finished(job):
    return job.state == "done" or job.state == "failed" or job.state == "cancelled"


def render(rows, fmt: str):
    match OutputFormat(fmt):
        case OutputFormat.CSV:
            return write_csv(rows)
        case OutputFormat.JSON:
            return write_json(rows)


def first_word(text):
    if text == "":
        return None
    return text.split()[0]


def request_headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def on_webhook(payload):
    if payload.get("action") == "opened":
        notify_reviewers(payload["pull_request"])


def is_python_source(path):
    return path.suffix == ".py"
