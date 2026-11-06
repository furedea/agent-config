from dataclasses import dataclass


@dataclass(frozen=True)
class EmailAddress:
    value: str

    def __post_init__(self):
        if "@" not in self.value:
            raise ValueError("bad email")

    def domain(self):
        return self.value.split("@")[1]


@dataclass(frozen=True)
class Percentage:
    value: float

    def __post_init__(self):
        if not 0 <= self.value <= 100:
            raise ValueError("out of range")


def apply_discount(price, discount: Percentage):
    return price * (1 - discount.value / 100)


def mail_domain(email: EmailAddress):
    return email.domain()


def render_name(name: str):
    return name.title()


def email_domain(email: str):
    if "@" not in email:
        raise ValueError("bad email")
    return email.split("@")[1]


def apply_percentage_off(price: float, percent: float):
    if not 0 <= percent <= 100:
        raise ValueError("out of range")
    return price * (1 - percent / 100)


def normalize_phone(phone: str):
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) != 10:
        raise ValueError("bad phone")
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
