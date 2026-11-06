import os


def get_user_name(user):
    return user.first_name + " " + user.last_name


def is_expired(token, now):
    return token.expires_at <= now


def count_active(sessions):
    return sum(1 for session in sessions if session.active)


def get_next_id(counter):
    counter.value += 1
    return counter.value


def is_ready(service):
    service.connect()
    return service.connected


def find_config(path):
    if not os.path.exists(path):
        with open(path, "w") as handle:
            handle.write("{}")
    with open(path) as handle:
        return handle.read()
