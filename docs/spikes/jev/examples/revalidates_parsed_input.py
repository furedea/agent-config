from dataclasses import dataclass


@dataclass(frozen=True)
class Port:
    value: int

    def __post_init__(self):
        if not 0 < self.value < 65536:
            raise ValueError("port out of range")


@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self):
        if "@" not in self.value:
            raise ValueError("bad email")


def parse_port(text: str) -> Port:
    return Port(int(text))


def open_socket(host, port: Port):
    return (host, port.value)


def send_welcome(email: Email, mailer):
    return mailer.send(email.value, "welcome")


def connect(host, port: Port):
    if not isinstance(port, Port):
        raise TypeError("port must be Port")
    if not 0 < port.value < 65536:
        raise ValueError("port out of range")
    return (host, port.value)


def notify(email: Email, mailer):
    if email is None or "@" not in email.value:
        raise ValueError("bad email")
    return mailer.send(email.value, "hello")


def listen(port: Port):
    if port.value <= 0 or port.value > 65535:
        return None
    return port.value
