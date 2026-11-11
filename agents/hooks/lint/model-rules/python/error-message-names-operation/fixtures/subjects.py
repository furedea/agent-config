"""Subjects for the error-message-names-operation eval; labels are in ../expect.yml. Never imported or run."""


def secret_path_reason(value, rule):
    return f"secret path policy matched.\n\nPath: {value}\nPattern: {rule['pattern']}\n\nWhy:\n  {rule['reason']}"


# Clean, from a real false positive: the message is built by another function that names the operation and subject.
def reject_secret_path(value, rules):
    for rule in rules:
        if rule.matches(value):
            raise ValueError(secret_path_reason(value, rule))


# Clean: names the operation and the subject.
def read_port(path):
    text = path.read_text()
    if not text.strip().isdigit():
        raise ValueError(f"cannot read the port from {path}: expected digits, got {text!r}")
    return int(text)


# Clean: wraps a cause and names the operation and the subject.
def load_settings(path):
    try:
        return path.read_text()
    except OSError as error:
        raise RuntimeError(f"cannot load settings from {path}") from error


# Clean: the raise inside the try is caught by the same function; only the wrapped error, which names the operation
# and the path, leaves it.
def project_targets(path, parse):
    try:
        if not path.exists():
            raise FileNotFoundError(path)
        return parse(path)
    except (OSError, ValueError) as error:
        raise RuntimeError(f"cannot read the project targets from {path}") from error


# Clean: rethrows a caught error unchanged.
def run_step(step):
    try:
        return step()
    except ValueError:
        raise


# Bad: a generic message.
def parse_count(text):
    if not text.isdigit():
        raise ValueError("invalid")
    return int(text)


# Bad: no message at all.
def open_session(name, sessions):
    if name not in sessions:
        raise KeyError()
    return sessions[name]


# Bad: names only the subject.
def delete_record(record_id, records):
    if record_id not in records:
        raise LookupError(f"{record_id}")
    del records[record_id]


# Bad: names only the operation.
def send_report(report, outbox):
    if not outbox.is_open:
        raise RuntimeError("send failed")
    outbox.put(report)
