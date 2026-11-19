import time


def count_active(users):
    count = 0
    # loop over users
    for user in users:
        # increment the counter
        if user.active:
            count += 1
    # return the count
    return count


def apply_discount(order, rate):
    # Multiply the total by one minus the rate.
    return order.total * (1 - rate)


def process(batch, store):
    # --- validation ---
    valid = [item for item in batch if item.sku and item.quantity > 0]
    # --- persistence ---
    store.save_all(valid)
    # --- reporting ---
    return len(valid), len(batch) - len(valid)


def to_euros(cents):
    # The payment API reports cents; every caller works in euros.
    return cents / 100


def retry(call, attempts):
    for attempt in range(attempts):
        try:
            return call()
        except TimeoutError:
            # Back off exponentially: the upstream rate limiter resets after about 2**n seconds.
            time.sleep(2**attempt)
    raise TimeoutError(f"call failed after {attempts} attempts")


def send(request, session):
    # httpx 0.27 drops this header on redirect (encode/httpx#3123); set it again on every request.
    request.headers["Authorization"] = session.token
    return session.send(request)


def sort_orders(orders):
    # Sort by id first: callers rely on a stable order for ties on the date.
    return sorted(sorted(orders, key=lambda order: order.id), key=lambda order: order.date)


def total_weight(items):
    """Return the total weight of the items in kilograms."""
    return sum(item.weight_kg * item.quantity for item in items)


# Return the sum of the prices.
def total_price(items):
    return sum(item.price for item in items)


# Kept for v1 webhook clients until they move to the v2 payload (#412).
def legacy_total(payload):
    return payload["amount"]
