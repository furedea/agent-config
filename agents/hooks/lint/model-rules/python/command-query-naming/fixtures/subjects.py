"""Subjects for the command-query-naming eval; labels are in ../expect.yml. Never imported or run."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

CALL_LOG: list[str] = []
_PORTS: dict[str, int] = {}


# Clean, from a real false positive: "check" promises neither a pure read nor an effect, and the body does both.
def check_paths(mode, payload, rules, audit_log, refusal):
    context = normalized(payload)
    for value in candidates_of(mode, context):
        if rule := blocked_rule(value, rules):
            audit_log.blocked(refusal(mode, value, context))
            raise ValueError(reason_for(value, rule))
    return 0


# Clean, from a real false positive: "judge" promises neither a pure read nor an effect.
@dataclass(frozen=True)
class Review:
    cache: Path

    def judge(self, plan, deadline):
        with file_lock(self.cache.parent / ".lock", timeout=deadline.remaining(5.0)):
            output = run_child(plan.arguments, deadline.remaining(60.0))
        return parse_judgement(output, plan)


# Clean: a command that returns the result of its own effect.
def save_report(path, report):
    path.write_text(json.dumps(report))
    return path.stat().st_size


# Clean: a memoizing query writes only its own cache.
def get_port(name):
    if name not in _PORTS:
        _PORTS[name] = int(os.environ[f"{name.upper()}_PORT"])
    return _PORTS[name]


# Clean: a pure lookup named as one.
def find_owner(repositories, name):
    for repository in repositories:
        if repository.name == name:
            return repository.owner
    return None


# Clean: a conventional terse name that the body fits.
def to_slug(title):
    return "-".join(title.lower().split())


# Bad: a query name whose body appends to a module-level log.
def get_user_count(users):
    CALL_LOG.append("get_user_count")
    return len(users)


# Bad: a command name whose body only computes a value the caller needs.
def save_total(prices):
    return sum(prices)


# Bad: a predicate name whose body deletes a file.
def is_stale(path, limit):
    if path.stat().st_mtime < limit:
        path.unlink()
        return True
    return False


# Bad: a command name whose body only builds a string and performs no update.
def update_label(item):
    return f"{item.name} ({item.count})"


# Bad: a query name whose body empties the argument it counted.
def count_items(items):
    total = len(items)
    items.clear()
    return total


# Bad: a query name whose body sends a request.
def find_user(users, name):
    requests.post("https://audit.example.com/lookups", json={"name": name})
    return users.get(name)


# Bad: a command name whose body returns the surviving entries and deletes nothing.
def delete_expired(entries, now):
    return [entry for entry in entries if entry.expires_at > now]


# Bad: a command name whose body returns a converted number and sets nothing.
def set_timeout(config, seconds):
    return seconds * 1000


# Clean: a command that returns the results of the effects it performs.
def run_all(tasks):
    return [task.run() for task in tasks]


# Clean: a pure conversion named as one.
def to_dict(user):
    return {"name": user.name, "count": user.count}
