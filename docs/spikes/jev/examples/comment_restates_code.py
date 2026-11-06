def retry_delay_seconds(attempt):
    # The upstream API rate-limits per minute, so cap the backoff at 60 s.
    return min(2**attempt, 60)


def to_cents(amount):
    # round() would use banker's rounding and disagree with the ledger.
    return int(amount * 100 + 0.5)


def first_enabled(flags):
    # The legacy client sends "0" for disabled and omits the key for unset.
    return next((flag for flag in flags if flag != "0"), None)


def add_tax(price, rate):
    # multiply price by rate
    tax = price * rate
    # add tax to price
    total = price + tax
    # return the total
    return total


def build_names(users):
    # create an empty list
    names = []
    # loop over users
    for user in users:
        # append the name
        names.append(user.name)
    return names


def is_adult(person):
    # check if age is at least 18
    return person.age >= 18
